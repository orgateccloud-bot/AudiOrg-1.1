"""
ORGATEC - Pipeline de auditoria bidirecional em background (v3 - Motor Forense).

Metodologia Big Four aplicada:
  - Score de suspeicao 0-100 por triangulacao (valor + volume + tempo + preco/cab)
  - Deteccao de leiloes orfaos (remessa sem arremate)
  - Balanco de inventario pecuario por mes
  - Deteccao de periodos inativos com plantel ativo
  - Classificacao bidirecional automatica via CPF (REM=RECEITA, DEST=DESPESA)
  - Deduplicacao por chave_acesso
"""

from __future__ import annotations

import logging
import os
import re
import secrets
import tempfile
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

from fastapi import UploadFile

from api.services.auditoria_tasks import tasks_status  # re-export para callers
from nfa_extractor.domain.extractor import extrair_notas

logger = logging.getLogger(__name__)

__all__ = ["tasks_status", "processar_lote_auditoria"]


# == Helpers basicos ===========================================================

def _norm_cpf(v: Any) -> str:
    """Remove mascara de CPF/CNPJ."""
    return re.sub(r"\D", "", str(v or ""))


def _parse_emissao(emissao: Any) -> datetime | None:
    """Converte string de emissao para datetime."""
    s = str(emissao or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None


def _cabecas_nota(n: Any) -> float:
    """Retorna total de cabecas de uma nota (soma produtos ou quantidade_total)."""
    produtos = getattr(n, "produtos", None) or []
    if produtos:
        try:
            return sum(float(getattr(p, "quantidade", 0) or 0) for p in produtos)
        except (TypeError, ValueError):
            pass
    try:
        return float(getattr(n, "quantidade_total", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


# == Score de suspeicao (Big Four) =============================================

def _calcular_score_triangulacao(
    s_list: list,
    e_list: list,
    total_saida: float,
    total_entrada: float,
    menor_gap: int | None,
) -> int:
    """
    Score de suspeicao 0-100 (metodologia Big Four).

    Dimensoes avaliadas:
      - Equivalencia de valor  (0-40 pts): valor identico = nota-espelho classica
      - Equivalencia de volume (0-30 pts): mesmas cabecas = mesma leva fisica
      - Proximidade temporal   (0-20 pts): D+0/D+1 impossivel fisicamente em longas distancias
      - Equivalencia de preco  (0-10 pts): mesmo R$/cabeca elimina negociacao real
    """
    score = 0

    # 1. Equivalencia de valor (40 pts)
    if total_saida > 0 and total_entrada > 0:
        ratio_val = min(total_saida, total_entrada) / max(total_saida, total_entrada)
        if ratio_val >= 0.99:
            score += 40
        elif ratio_val >= 0.95:
            score += 28
        elif ratio_val >= 0.90:
            score += 15
        elif ratio_val >= 0.80:
            score += 5

    # 2. Equivalencia de volume em cabecas (30 pts)
    cab_s = sum(_cabecas_nota(n) for n in s_list)
    cab_e = sum(_cabecas_nota(n) for n in e_list)
    if cab_s > 0 and cab_e > 0:
        ratio_cab = min(cab_s, cab_e) / max(cab_s, cab_e)
        if ratio_cab >= 0.99:
            score += 30
        elif ratio_cab >= 0.95:
            score += 20
        elif ratio_cab >= 0.80:
            score += 10
        elif ratio_cab >= 0.60:
            score += 5

    # 3. Proximidade temporal (20 pts)
    if menor_gap is not None:
        if menor_gap == 0:
            score += 20
        elif menor_gap <= 1:
            score += 18
        elif menor_gap <= 3:
            score += 14
        elif menor_gap <= 7:
            score += 10
        elif menor_gap <= 14:
            score += 5
        elif menor_gap <= 30:
            score += 2

    # 4. Equivalencia de preco por cabeca (10 pts)
    try:
        preco_s = total_saida / cab_s if cab_s > 0 else 0
        preco_e = total_entrada / cab_e if cab_e > 0 else 0
        if preco_s > 0 and preco_e > 0:
            ratio_p = min(preco_s, preco_e) / max(preco_s, preco_e)
            if ratio_p >= 0.99:
                score += 10
            elif ratio_p >= 0.95:
                score += 7
            elif ratio_p >= 0.90:
                score += 3
    except ZeroDivisionError:
        pass

    return min(score, 100)


# == Deteccao de triangulacoes ================================================

def _detectar_triangulacoes(notas: list, client_cpf_norm: str) -> list[dict]:
    """
    Detecta operacoes circulares com score de suspeicao 0-100.

    Classificacao por score:
      - CRITICO >= 70: possivel nota-espelho (round-trip ficticio)
      - MEDIO   >= 40: relacao bilateral suspeita
      - BAIXO    < 40: relacao bilateral comum (menos relevante)
    """
    saidas_por_cp: dict[str, list] = defaultdict(list)
    entradas_por_cp: dict[str, list] = defaultdict(list)

    for n in notas:
        rem = getattr(n, "remetente", None)
        dest = getattr(n, "destinatario", None)
        rem_cpf = _norm_cpf(getattr(rem, "cpf_cnpj", None))
        dest_cpf = _norm_cpf(getattr(dest, "cpf_cnpj", None))

        if rem_cpf == client_cpf_norm:
            saidas_por_cp[dest_cpf].append(n)
        elif dest_cpf == client_cpf_norm:
            entradas_por_cp[rem_cpf].append(n)

    triangulacoes: list[dict] = []

    for cp_cpf in set(saidas_por_cp) & set(entradas_por_cp):
        if not cp_cpf or len(cp_cpf) not in (11, 14):
            continue

        s_list = saidas_por_cp[cp_cpf]
        e_list = entradas_por_cp[cp_cpf]

        total_saida = sum(getattr(n, "valor_total", 0) or 0 for n in s_list)
        total_entrada = sum(getattr(n, "valor_total", 0) or 0 for n in e_list)

        datas_s = [d for d in (_parse_emissao(getattr(n, "emissao", "")) for n in s_list) if d]
        datas_e = [d for d in (_parse_emissao(getattr(n, "emissao", "")) for n in e_list) if d]
        menor_gap: int | None = None
        if datas_s and datas_e:
            menor_gap = min(abs((ds - de).days) for ds in datas_s for de in datas_e)

        score = _calcular_score_triangulacao(
            s_list, e_list, total_saida, total_entrada, menor_gap
        )

        if score >= 70:
            severidade = "CRITICO"
        elif score >= 40:
            severidade = "MEDIO"
        else:
            severidade = "BAIXO"

        cp_nome = ""
        if s_list:
            cp_nome = getattr(getattr(s_list[0], "destinatario", None), "nome", "") or ""
        if not cp_nome and e_list:
            cp_nome = getattr(getattr(e_list[0], "remetente", None), "nome", "") or ""

        cab_s = sum(_cabecas_nota(n) for n in s_list)
        cab_e = sum(_cabecas_nota(n) for n in e_list)

        triangulacoes.append({
            "cp_cpf": cp_cpf,
            "cp_nome": cp_nome,
            "total_saida": total_saida,
            "total_entrada": total_entrada,
            "saldo": total_saida - total_entrada,
            "n_saidas": len(s_list),
            "n_entradas": len(e_list),
            "cab_saida": cab_s,
            "cab_entrada": cab_e,
            "preco_med_saida": round(total_saida / cab_s, 2) if cab_s > 0 else None,
            "preco_med_entrada": round(total_entrada / cab_e, 2) if cab_e > 0 else None,
            "menor_gap_dias": menor_gap,
            "score": score,
            "severidade": severidade,
        })

    # Ordena do mais suspeito para o menos suspeito
    triangulacoes.sort(key=lambda x: -x["score"])
    return triangulacoes


# == Leiloes orfaos ============================================================

def _detectar_leilao_orfao(notas: list, client_cpf_norm: str) -> list[dict]:
    """
    Detecta notas de REMESSA/LEILAO sem NF-e de arremate correspondente.
    Uma remessa sem retorno pode indicar receita omitida.
    """
    orfaos = []
    for n in notas:
        natureza = str(getattr(n, "natureza", "") or "").upper()
        if "LEILAO" not in natureza and "LEIL" not in natureza:
            continue
        rem_cpf = _norm_cpf(getattr(getattr(n, "remetente", None), "cpf_cnpj", None))
        if rem_cpf != client_cpf_norm:
            continue
        orfaos.append({
            "numero": getattr(n, "numero", "?"),
            "emissao": getattr(n, "emissao", ""),
            "valor": getattr(n, "valor_total", 0) or 0,
            "cabecas": _cabecas_nota(n),
            "leiloeiro": getattr(getattr(n, "destinatario", None), "nome", "") or "",
        })
    return orfaos


# == Balanco de inventario =====================================================

def _calcular_balanco_inventario(notas: list, client_cpf_norm: str) -> dict:
    """
    Apura balanco de inventario pecuario por mes.
    Identifica meses com plantel ativo e zero vendas (sinal de saidas informais).
    """
    entradas_mes: dict[str, float] = Counter()
    saidas_mes: dict[str, float] = Counter()

    for n in notas:
        dt = _parse_emissao(getattr(n, "emissao", ""))
        if not dt:
            continue
        mes_key = dt.strftime("%Y-%m")
        cab = _cabecas_nota(n)
        natureza = str(getattr(n, "natureza", "") or "").upper()

        rem_cpf = _norm_cpf(getattr(getattr(n, "remetente", None), "cpf_cnpj", None))
        dest_cpf = _norm_cpf(getattr(getattr(n, "destinatario", None), "cpf_cnpj", None))

        if dest_cpf == client_cpf_norm:
            entradas_mes[mes_key] += cab
        elif rem_cpf == client_cpf_norm and "TRANSFER" not in natureza:
            saidas_mes[mes_key] += cab

    todos_meses = sorted(set(entradas_mes) | set(saidas_mes))
    saldo_acumulado = 0.0
    meses_sem_venda: list[str] = []
    historico = []

    for mes in todos_meses:
        e = entradas_mes.get(mes, 0)
        s = saidas_mes.get(mes, 0)
        saldo_acumulado += e - s
        historico.append({
            "mes": mes,
            "entradas": e,
            "saidas": s,
            "saldo_mes": e - s,
            "saldo_acumulado": saldo_acumulado,
        })
        # Mes com plantel ativo (>= 50 cab) e zero saidas e atipico
        if s == 0 and saldo_acumulado >= 50:
            meses_sem_venda.append(mes)

    return {
        "historico": historico,
        "saldo_final": saldo_acumulado,
        "meses_sem_venda_com_plantel": meses_sem_venda,
    }


# == Formatacao dos achados adicionais =========================================

def _formatar_achados_adicionais(leiloes_orfaos: list[dict], balanco: dict) -> str:
    """Texto de leiloes orfaos e inventario para o veredito."""
    linhas: list[str] = []

    if leiloes_orfaos:
        linhas += [
            "## LEILOES SEM NOTA DE ARREMATE",
            "",
        ]
        for lo in leiloes_orfaos:
            linhas.append(
                f"- NFA {lo['numero']} ({lo['emissao']}): {lo['cabecas']:.0f} cab."
                f" para {lo['leiloeiro']} | R$ {lo['valor']:,.2f}"
                " — exigir NF-e modelo 55 de arremate ou nota de retorno."
            )
        linhas.append("")

    saldo = balanco.get("saldo_final", 0)
    meses_inativos = balanco.get("meses_sem_venda_com_plantel", [])

    if saldo > 20 or meses_inativos:
        linhas += ["## BALANCO DE INVENTARIO", ""]
        if saldo > 20:
            linhas.append(
                f"Cabecas sem destino documentado ao final do periodo: {saldo:.0f} cab."
                " Verificar estoque em formacao (CAEPF + SiCAR),"
                " mortalidade documentada ou saidas informais."
            )
        if meses_inativos:
            linhas.append(
                f"Meses com plantel ativo (>= 50 cab.) e ZERO saidas: {', '.join(meses_inativos)}."
                " Investigar pastejo externo, saidas informais ou mortalidade nao documentada."
            )
        linhas.append("")

    return "\n".join(linhas)


def _formatar_triangulacoes(triangulacoes: list[dict]) -> str:
    """Gera texto descritivo das triangulacoes para o veredito IA."""
    if not triangulacoes:
        return ""

    n_critico = sum(1 for t in triangulacoes if t["severidade"] == "CRITICO")
    n_medio = sum(1 for t in triangulacoes if t["severidade"] == "MEDIO")

    linhas = [
        "## OPERACOES CIRCULARES - CRUZAMENTO REM x DEST",
        "",
        f"Contrapartes bilaterais: {len(triangulacoes)} ({n_critico} CRITICO, {n_medio} MEDIO)",
        "",
    ]

    for i, t in enumerate(triangulacoes, 1):
        gap_txt = f"{t['menor_gap_dias']} dia(s)" if t["menor_gap_dias"] is not None else "N/D"
        ps = f"R$ {t['preco_med_saida']:,.2f}/cab" if t.get("preco_med_saida") else "N/D"
        pe = f"R$ {t['preco_med_entrada']:,.2f}/cab" if t.get("preco_med_entrada") else "N/D"

        linhas += [
            f"### {i}. {t['cp_nome']} | CPF {t['cp_cpf']} | Score {t['score']}/100 [{t['severidade']}]",
            f"- Saidas: {t['n_saidas']} nota(s) | {t.get('cab_saida',0):.0f} cab."
            f" | R$ {t['total_saida']:,.2f} | preco medio {ps}",
            f"- Entradas: {t['n_entradas']} nota(s) | {t.get('cab_entrada',0):.0f} cab."
            f" | R$ {t['total_entrada']:,.2f} | preco medio {pe}",
            f"- Saldo: R$ {t['saldo']:,.2f} | Gap minimo: {gap_txt}",
            "",
        ]

    linhas += [
        "Score >= 70: possivel nota-espelho (round-trip ficticio).",
        "Score 40-69: relacao bilateral suspeita — exige investigacao.",
        "Cruzamento obrigatorio: GTA AGRODEFESA-GO + extrato bancario + contrato compra/venda.",
    ]

    return "\n".join(linhas)


# == Pipeline principal ========================================================

async def processar_lote_auditoria(
    task_id: str,
    files: list[UploadFile],
    client_name: str,
    client_cpf: str,
) -> None:
    """
    Pipeline bidirecional em background (v3 - Motor Forense Big Four).

    Aceita N PDFs/XMLs (REM + DEST + outros). Combina, deduplica,
    aplica motor forense completo e gera laudo OrgAudi com achados TR-XX.
    """
    from nfa_extractor.infrastructure.database_v2 import SessionLocal

    db = SessionLocal()
    try:
        tasks_status[task_id] = {"status": "extraindo", "progress": 10}

        # -- Extracao ----------------------------------------------------------
        all_notas: list = []
        temp_dir = tempfile.gettempdir()

        for file in files:
            ext = os.path.splitext(file.filename or "")[1].lower()
            if ext not in {".pdf", ".xml"}:
                logger.warning("Extensao rejeitada: %s", ext)
                continue

            safe_name = f"{secrets.token_hex(8)}{ext}"
            file_path = os.path.join(temp_dir, safe_name)
            try:
                with open(file_path, "wb") as buf:
                    content = await file.read()
                    buf.write(content)
                notas, _, _ = extrair_notas(file_path)
                all_notas.extend(notas)
                logger.info("Arquivo '%s': %d notas extraidas", file.filename, len(notas))
            except Exception as exc:
                logger.error("Erro ao extrair '%s': %s", file.filename, exc)
            finally:
                try:
                    os.remove(file_path)
                except OSError:
                    pass

        # -- Deduplicacao por chave_acesso -------------------------------------
        seen: set[str] = set()
        notas_unicas: list = []
        for n in all_notas:
            key = getattr(n, "chave_acesso", None) or getattr(n, "numero", None)
            if key and key not in seen:
                seen.add(key)
                notas_unicas.append(n)
            elif not key:
                notas_unicas.append(n)

        if not notas_unicas:
            tasks_status[task_id] = {
                "status": "erro", "progress": 100,
                "erro": "Nenhuma nota fiscal extraida dos arquivos enviados.",
            }
            return

        logger.info(
            "Deduplicacao: %d notas unicas (de %d originais, %d duplicatas removidas)",
            len(notas_unicas), len(all_notas), len(all_notas) - len(notas_unicas),
        )

        # -- Motor forense Big Four -------------------------------------------
        tasks_status[task_id] = {"status": "analise_forense", "progress": 35}

        client_cpf_norm = _norm_cpf(client_cpf)

        # 1. Triangulacoes com score 0-100
        triangulacoes = _detectar_triangulacoes(notas_unicas, client_cpf_norm)
        texto_triangulacoes = _formatar_triangulacoes(triangulacoes)

        # 2. Leiloes sem arremate
        leiloes_orfaos = _detectar_leilao_orfao(notas_unicas, client_cpf_norm)

        # 3. Balanco de inventario
        balanco = _calcular_balanco_inventario(notas_unicas, client_cpf_norm)

        texto_adicionais = _formatar_achados_adicionais(leiloes_orfaos, balanco)

        n_criticos = sum(1 for t in triangulacoes if t["severidade"] == "CRITICO")
        if n_criticos:
            logger.warning(
                "%d triangulacao(oes) CRITICA(S) detectada(s) para %s (scores: %s)",
                n_criticos, client_name,
                [t["score"] for t in triangulacoes if t["severidade"] == "CRITICO"],
            )

        # -- Squad IA ----------------------------------------------------------
        tasks_status[task_id] = {"status": "analisando_ia", "progress": 55}

        veredito_ia = ""
        try:
            from nfa_extractor.application.agents_engine import rodar_auditoria_completa
            analise_state = rodar_auditoria_completa(notas_unicas, client_name)
            veredito_ia = analise_state.get("veredito_final", "")
        except Exception as exc:
            logger.warning("Squad IA indisponivel (%s) — prosseguindo.", exc)

        # Triangulacoes e achados adicionais vao como texto no veredito IA
        # e como achados formais TR-XX/LO-XX no adapter OrgAudi
        veredito_completo = "\n\n".join(
            filter(None, [veredito_ia, texto_triangulacoes, texto_adicionais])
        )

        # -- Geracao do laudo OrgAudi -----------------------------------------
        tasks_status[task_id] = {"status": "gerando_pdf", "progress": 80}

        os.makedirs(os.path.join("data", "laudos"), exist_ok=True)
        nome_safe = re.sub(r"[^A-Za-z0-9]", "_", client_name.upper())[:50].strip("_")
        pdf_filename = f"Laudo_{nome_safe}_{client_cpf_norm}.pdf"
        pdf_path = os.path.join("data", "laudos", pdf_filename)

        try:
            from pdf_engine import gerar_laudo_orgaudi  # unificado em pdf_engine/orgaudi/
            gerar_laudo_orgaudi(
                notas=notas_unicas,
                cliente_nome=client_name,
                cliente_cpf=client_cpf,
                saida=pdf_path,
                veredito_ia=veredito_completo or None,
                triangulacoes=triangulacoes or None,
            )
            logger.info("Laudo OrgAudi gerado: %s", pdf_path)
        except Exception as exc:
            logger.error("Erro ao gerar laudo OrgAudi: %s", exc, exc_info=True)
            tasks_status[task_id] = {
                "status": "erro", "progress": 100,
                "erro": f"Falha ao gerar PDF: {exc}",
            }
            return

        valor_total = sum(getattr(n, "valor_total", 0) or 0 for n in notas_unicas)

        tasks_status[task_id] = {
            "status": "concluido",
            "progress": 100,
            "pdf_path": pdf_path,
            "pdf_filename": pdf_filename,
            "total_notas": len(notas_unicas),
            "valor_total": valor_total,
            "triangulacoes_detectadas": len(triangulacoes),
            "triangulacoes_criticas": n_criticos,
            "score_maximo": max((t["score"] for t in triangulacoes), default=0),
            "leiloes_orfaos": len(leiloes_orfaos),
            "cabecas_sem_destino": int(balanco.get("saldo_final", 0)),
            "meses_inativos": len(balanco.get("meses_sem_venda_com_plantel", [])),
        }

    except Exception as exc:
        logger.error("Erro fatal na task %s: %s", task_id, exc, exc_info=True)
        tasks_status[task_id] = {
            "status": "erro", "progress": 100, "erro": str(exc),
        }
    finally:
        db.close()
