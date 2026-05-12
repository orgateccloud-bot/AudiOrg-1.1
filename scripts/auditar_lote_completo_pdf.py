"""Auditoria completa: todos PDFs -> agentes S1..S7 -> 1 PDF por cliente.

Pipeline por produtor:
    1. Extrai NFAs raw (nfa-repo)
    2. Converte para dicts (nfa_bridge)
    3. Roda Orchestrator (S1..S7 com pf-gate)
    4. Captura parecer dos agentes + erros
    5. Gera laudo PDF via gerar_laudo_v250 (modelo OrgAudi v2.5.0)
    6. Salva parecer LLM em JSON ao lado do PDF

Saidas:
    reports_nfa/laudos_pdf/Laudo_<NOME>.pdf
    reports_nfa/laudos_pdf/Laudo_<NOME>.json   (parecer agentes)
    reports_nfa/lote_completo_<ts>.json         (resumo global + custo)

Uso:
    python -m scripts.auditar_lote_completo_pdf
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import traceback
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Carrega config.env (ANTHROPIC_API_KEY etc.) antes de qualquer import LLM
_CONFIG = ROOT / "config.env"
if _CONFIG.exists():
    for linha in _CONFIG.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))

PASTA_PDFS = Path(r"C:\Users\Veloso\Desktop\NFE_GADO_2026\ARQUIVO_2026_RESUMO_DE_NFE_GADO_2026")
DESTINO_PDF = ROOT / "reports_nfa" / "laudos_pdf"
DESTINO_RESUMO = ROOT / "reports_nfa"

AGENTES = ["S1", "S2", "S3", "S4", "S5", "S6", "S7"]


def _ascii(s) -> str:
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii")


def _slug(nome: str) -> str:
    return _ascii(nome).strip().replace(" ", "_") or "Sem_Nome"


def _extrair_produtor(nome: str, pdfs_por_pos: dict) -> tuple[list, list, str, str]:
    """Extrai NFAs raw + dicts de todos os PDFs do produtor.

    Retorna (nfas_raw, notas_dicts, cpf_contribuinte, nome_real).
    """
    from src.domain.extractor import extrair_notas

    from horizon_blue_one.nfa_bridge import nfa_to_dict

    nfas_raw: list = []
    dicts: list = []
    cpf = ""
    nome_real = nome

    # Primeira passagem: descobrir CPF
    for posicao, lista in pdfs_por_pos.items():
        for pdf in lista:
            try:
                notas, n_extraido, c_extraido = extrair_notas(str(pdf))
            except Exception:
                continue
            if c_extraido and not cpf:
                cpf = c_extraido
            if n_extraido and (not nome_real or not nome_real.strip()):
                nome_real = n_extraido
            for nfa in notas:
                nfas_raw.append(nfa)
                dicts.append(nfa_to_dict(nfa, cpf or c_extraido, posicao))

    return nfas_raw, dicts, cpf, nome_real


async def auditar_um(nome: str, pdfs_por_pos: dict, orch) -> dict:
    """Pipeline completo para 1 produtor."""
    from horizon_blue_one.core.precalc import precalcular
    from horizon_blue_one.core.token_router import snapshot_stats

    t0 = time.time()
    res: dict = {"produtor": nome, "erros": []}

    # 1) Extracao
    try:
        nfas_raw, dicts, cpf, nome_real = _extrair_produtor(nome, pdfs_por_pos)
    except Exception as exc:
        res["erros"].append({"etapa": "extracao", "erro": str(exc)[:200]})
        return res

    res["cpf"] = cpf
    res["nome_real"] = nome_real
    res["n_notas"] = len(nfas_raw)

    if not nfas_raw:
        res["erros"].append({"etapa": "extracao", "erro": "PDFs vazios"})
        return res

    # 2) Pipeline LLM (Orchestrator com pf-gate)
    receita = sum(n["valor_total"] for n in dicts
                  if n["natureza"] == "VENDA" and n["posicao"] == "REMETENTE")
    despesa = sum(n["valor_total"] for n in dicts
                  if not (n["natureza"] == "VENDA" and n["posicao"] == "REMETENTE"))
    payload = {
        "produtor": nome,
        "notas": dicts,
        "contribuinte": {
            "razao_social":       nome_real or nome,
            "cpf_cnpj":           cpf,
            "inscricao_estadual": "12345678",
            "area_total_ha":      100,
            "area_utilizada_ha":  90,
        },
        "lcdpr_data": {
            "total_receitas": receita,
            "total_despesas": despesa,
        },
    }

    snap_in = snapshot_stats()
    try:
        payload = await precalcular(payload)
        pre = payload.get("__precalc__", {})
        res["score_precalc"] = pre.get("xgboost", {}).get("score")
        res["pf"] = pre.get("xgboost", {}).get("probabilidade_autuacao")

        resultados = await orch.executar_pipeline(
            payload,
            agentes=AGENTES,
            chamar_ceo_no_fim=True,
            paralelo=True,
            early_exit=False,
            max_tokens_orcamento=80_000,
        )
    except Exception as exc:
        res["erros"].append({"etapa": "orchestrator", "erro": str(exc)[:300]})
        resultados = {}
    snap_out = snapshot_stats()

    # 3) Coleta parecer
    res["agentes"] = {}
    for aid, r in resultados.items():
        out = r.output if isinstance(r.output, dict) else {"raw": str(r.output)}
        res["agentes"][aid] = {
            "status":     r.status,
            "confidence": round(r.confidence, 3),
            "output":     out,
        }
    def _tokens(snap):
        t = snap.get("resumo", {}).get("tokens_totais", {})
        return int(t.get("input", 0)) + int(t.get("output", 0))

    def _custo(snap):
        return float(snap.get("resumo", {}).get("custo_total_usd", 0) or 0)

    res["tokens_consumidos"] = _tokens(snap_out) - _tokens(snap_in)
    res["custo_usd_estimado"] = round(_custo(snap_out) - _custo(snap_in), 4)

    # 4) Gera PDF do laudo (modelo v2.5.0)
    DESTINO_PDF.mkdir(parents=True, exist_ok=True)
    pdf_path = DESTINO_PDF / f"Laudo_{_slug(nome_real or nome)}.pdf"
    try:
        from pdf_engine.orgaudi_v250.report_builder import gerar_laudo_v250
        gerar_laudo_v250(
            notas=nfas_raw,
            cliente_nome=nome_real or nome,
            cliente_cpf=cpf or "00000000000",
            saida=pdf_path,
            municipio="Formoso",
            estado="GO",
        )
        res["pdf"] = str(pdf_path)
    except Exception as exc:
        res["erros"].append({"etapa": "pdf", "erro": str(exc)[:300],
                             "trace": traceback.format_exc()[-400:]})
        res["pdf"] = None

    # 5) Salva parecer JSON ao lado
    try:
        json_path = DESTINO_PDF / f"Laudo_{_slug(nome_real or nome)}.json"
        json_path.write_text(
            json.dumps({
                "produtor":          nome,
                "nome_real":         nome_real,
                "cpf":               cpf,
                "score_precalc":     res.get("score_precalc"),
                "pf":                res.get("pf"),
                "agentes":           res["agentes"],
                "tokens":            res["tokens_consumidos"],
                "custo_usd":         res["custo_usd_estimado"],
            }, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        res["parecer_json"] = str(json_path)
    except Exception as exc:
        res["erros"].append({"etapa": "json_parecer", "erro": str(exc)[:200]})

    res["latencia_ms"] = round((time.time() - t0) * 1000)
    return res


async def main() -> None:
    from horizon_blue_one.core.orchestrator import Orchestrator
    from horizon_blue_one.core.token_router import snapshot_stats
    from horizon_blue_one.nfa_bridge import agrupar_pdfs_por_produtor

    print(f"\n{'='*78}")
    print("AUDITORIA LOTE COMPLETO - todos PDFs (S1..S7) -> PDF por cliente")
    print(f"{'='*78}\n")

    if not PASTA_PDFS.exists():
        print(f"ERRO: pasta de PDFs nao encontrada: {PASTA_PDFS}")
        sys.exit(1)

    grupos = agrupar_pdfs_por_produtor(PASTA_PDFS)
    print(f"Produtores identificados: {len(grupos)}")
    for nome, p in grupos.items():
        rem = len(p.get("REMETENTE", []))
        dst = len(p.get("DESTINATARIO", []))
        print(f"  - {nome:<20} REM={rem} DEST={dst}")
    print()

    orch = Orchestrator()
    relatorios: list[dict] = []
    snap_total_in = snapshot_stats()
    t_total = time.time()

    for nome, pdfs in grupos.items():
        print(f"[{nome}]...", flush=True)
        try:
            r = await auditar_um(nome, pdfs, orch)
        except Exception as exc:
            r = {"produtor": nome, "erros": [{"etapa": "fatal", "erro": str(exc)[:300]}]}
        relatorios.append(r)

        notas = r.get("n_notas", 0)
        agentes = r.get("agentes", {}) or {}
        statuses = ",".join(f"{aid}:{a['status'][:4]}" for aid, a in agentes.items())
        pdf_ok = "OK" if r.get("pdf") else "ERR"
        print(f"  notas={notas} pdf={pdf_ok} agentes={statuses or '(none)'}")
        for e in r.get("erros", []):
            print(f"    [ERR {e.get('etapa')}] {e.get('erro')}")

    elapsed = time.time() - t_total
    snap_total_out = snapshot_stats()

    DESTINO_RESUMO.mkdir(parents=True, exist_ok=True)
    saida = DESTINO_RESUMO / f"lote_completo_{int(time.time())}.json"
    saida.write_text(
        json.dumps({
            "elapsed_s":    round(elapsed, 1),
            "n_produtores": len(relatorios),
            "produtores":   relatorios,
            "stats_inicio": snap_total_in,
            "stats_fim":    snap_total_out,
            "custo_total_usd": round(
                float(snap_total_out.get("resumo", {}).get("custo_total_usd", 0) or 0)
                - float(snap_total_in.get("resumo", {}).get("custo_total_usd", 0) or 0),
                4,
            ),
            "tokens_total": (
                int(snap_total_out.get("resumo", {}).get("tokens_totais", {}).get("input", 0))
                + int(snap_total_out.get("resumo", {}).get("tokens_totais", {}).get("output", 0))
                - int(snap_total_in.get("resumo", {}).get("tokens_totais", {}).get("input", 0))
                - int(snap_total_in.get("resumo", {}).get("tokens_totais", {}).get("output", 0))
            ),
        }, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    print(f"\n{'-'*78}")
    print(f"Lote concluido: {len(relatorios)} produtores em {elapsed:.1f}s")
    print(f"PDFs em: {DESTINO_PDF}")
    print(f"Resumo:  {saida}")
    print(f"{'-'*78}\n")


if __name__ == "__main__":
    asyncio.run(main())
