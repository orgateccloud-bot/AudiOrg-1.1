"""Auditoria automatizada — ADELA FERNANDA SILVA SANTOS (2025) — v2 ENRIQUECIDA.

Mudancas v2:
- CFOPs preenchidos por natureza (5102 VENDA, 5151 TRANSF, 5904 LEILAO)
- IE remetente extraida dos PDFs
- Detector customizado de CARROSSEL_IDA_VOLTA (mesmo dia, mesmo valor, contraparte invertida)
- Detector customizado de DEVOLUCAO_AMPLIFICADA (CPF retorna com >150% das cabecas)
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import requests

API_BASE = "http://127.0.0.1:8082"
EMAIL = "teste@orgatec.com.br"
SENHA = "senha123"

ADELA_CPF = "069.311.951-90"
ADELA_NOME = "ADELA FERNANDA SILVA SANTOS"
ADELA_IE = "115254234"

# Mapa natureza -> CFOP (Goias intra-estado, produtor rural)
CFOP_POR_NATUREZA = {
    "VENDA":          "5102",  # Venda de mercadoria adquirida ou recebida de terceiros
    "TRANSFERENCIA":  "5151",  # Transferencia de producao do estabelecimento
    "REMESSA/LEILAO": "5904",  # Remessa para venda fora do estabelecimento
}

# (numero, data, natureza, valor, rem_cpf, rem_nome, rem_ie, cabecas, municipio_rem)
NOTAS_DEST = [
    ("25627606", "18/06/2025", "VENDA", 361080.00, "577.749.941-49", "DIVINO FERNANDES DOS SANTOS", "114562083", 124, "TROMBAS"),
    ("25661445", "24/06/2025", "VENDA",  12320.00, "104.956.191-08", "ANDRE FERNANDES DA SILVA",     "115732616",   4, "MONTIVIDIU DO NORTE"),
    ("25753672", "07/07/2025", "VENDA",  21240.00, "104.956.191-08", "ANDRE FERNANDES DA SILVA",     "115732616",   6, "MONTIVIDIU DO NORTE"),
    ("25813736", "16/07/2025", "VENDA", 105840.00, "604.849.181-68", "ADMILSON DA CAMARA ROMEIRO",   "114757941",  42, "MINACU"),
    ("25898987", "30/07/2025", "VENDA",  82640.00, "604.849.181-68", "ADMILSON DA CAMARA ROMEIRO",   "114757941",  31, "MINACU"),
    ("26058508", "25/08/2025", "VENDA",  47140.00, "104.956.191-08", "ANDRE FERNANDES DA SILVA",     "115732616",  17, "MONTIVIDIU DO NORTE"),
    ("26443937", "31/10/2025", "VENDA",  25200.00, "047.599.621-66", "JOAO WESLEY NOBREGA ROMEIRO",  "114965455",  10, "TROMBAS"),
]

# (numero, data, natureza, valor, dest_cpf, dest_nome, dest_ie, cabecas)
NOTAS_REM = [
    ("25177992", "03/04/2025", "VENDA",          100858.38, "577.749.941-49", "DIVINO FERNANDES DOS SANTOS",     "114562083", 48),
    ("25471529", "26/05/2025", "VENDA",           31068.91, "604.849.181-68", "ADMILSON DA CAMARA ROMEIRO",      "114979910", 10),
    ("25510606", "01/06/2025", "TRANSFERENCIA",   79859.79, "047.599.621-66", "JOAO WESLEY NOBREGA ROMEIRO",     "114965455", 27),
    ("25715829", "01/07/2025", "REMESSA/LEILAO",  34580.00, "27.372.042/0001-00", "LEILOES TROMBAS LTDA-ME",     "106881116", 13),
    ("25749054", "07/07/2025", "VENDA",            3599.00, "598.544.561-53", "JANE QUEIROZ DE ARAUJO SILVA",    "113659687",  1),
    ("25766138", "09/07/2025", "VENDA",          170800.00, "104.956.191-08", "ANDRE FERNANDES DA SILVA",        "115771433", 60),
    ("25813404", "16/07/2025", "REMESSA/LEILAO", 105840.00, "604.849.181-68", "ADMILSON DA CAMARA ROMEIRO",      "114757941", 42),
    ("25820292", "17/07/2025", "VENDA",           39204.00, "036.170.761-49", "OTAVIO GONCALVES MATIAS",         "110806999", 18),
    ("25855069", "23/07/2025", "VENDA",          101940.00, "104.956.191-08", "ANDRE FERNANDES DA SILVA",        "115771433", 45),
    ("25868512", "24/07/2025", "REMESSA/LEILAO",  59660.00, "33.442.191/0001-09", "BOI FORTE LEILOES LTDA",      "107601907", 19),
    ("25906436", "31/07/2025", "VENDA",           36300.00, "010.919.661-92", "HALISON MACEDO DOS SANTOS",       "115413367", 11),
    ("25910879", "31/07/2025", "REMESSA/LEILAO",  32760.00, "33.442.191/0001-09", "BOI FORTE LEILOES LTDA",      "107601907", 13),
    ("25932999", "05/08/2025", "VENDA",           26400.00, "057.395.221-37", "ANA PAULA FERREIRA DE MOURA",     "115662740",  8),
    ("25951265", "07/08/2025", "VENDA",           13100.00, "301.950.551-87", "LUIZ CARLOS DE PAIVA",            "112097901",  5),
    ("25955577", "07/08/2025", "VENDA",           20960.00, "460.241.666-72", "ERNANE DE ASSIS FREITAS",         "114199701",  8),
    ("26405785", "23/10/2025", "VENDA",           48300.00, "027.987.731-56", "GUSTAVO VIEIRA DE OLIVEIRA",      "114772487", 15),
    ("26476918", "06/11/2025", "REMESSA/LEILAO",  15120.00, "33.442.191/0001-09", "BOI FORTE LEILOES LTDA",      "107601907",  6),
    ("26514714", "13/11/2025", "VENDA",            6240.00, "890.755.441-20", "SERGIO FLAUZINO DA SILVA",        "114950091",  2),
    ("26536562", "18/11/2025", "VENDA",           10920.00, "225.751.701-68", "ANTONIO RODRIGUES NETO",          "114800944",  4),
]


def _data_iso(data_br: str) -> str:
    return datetime.strptime(data_br, "%d/%m/%Y").strftime("%Y-%m-%d")


def montar_payload() -> dict:
    notas = []

    for num, data, nat, valor, rem_cpf, rem_nome, rem_ie, cab, mun in NOTAS_DEST:
        notas.append({
            "numero": num,
            "data": _data_iso(data),
            "natureza": nat,
            "valor_total": valor,
            "remetente_cpf": rem_cpf,
            "remetente_nome": rem_nome,
            "destinatario_cpf": ADELA_CPF,
            "destinatario_nome": ADELA_NOME,
            "cfop": CFOP_POR_NATUREZA.get(nat, ""),
            "cabecas": cab,
            "municipio": mun,
            "ie_remetente": rem_ie,
            "posicao": "DESTINATARIO",
            "tipo_doc": "nfa-e",
            "atividade": "PRODUTOR_RURAL",
        })

    for num, data, nat, valor, dest_cpf, dest_nome, dest_ie, cab in NOTAS_REM:
        notas.append({
            "numero": num,
            "data": _data_iso(data),
            "natureza": nat,
            "valor_total": valor,
            "remetente_cpf": ADELA_CPF,
            "remetente_nome": ADELA_NOME,
            "destinatario_cpf": dest_cpf,
            "destinatario_nome": dest_nome,
            "cfop": CFOP_POR_NATUREZA.get(nat, ""),
            "cabecas": cab,
            "municipio": "TROMBAS",
            "ie_remetente": ADELA_IE,
            "posicao": "REMETENTE",
            "tipo_doc": "nfa-e",
            "atividade": "PRODUTOR_RURAL",
        })

    return {
        "contribuinte_cpf": ADELA_CPF,
        "contribuinte_nome": ADELA_NOME,
        "notas": notas,
        "is_pj": False,
        "is_segurado_especial": False,
    }


def deteccao_customizada(notas: list) -> dict:
    """Detectores complementares para padroes que os de produto nao captam."""
    alertas: list[dict] = []

    # 1. CARROSSEL IDA-E-VOLTA: mesmo dia, valores identicos, contraparte invertida
    por_dia_valor = defaultdict(list)
    for n in notas:
        chave = (n["data"], round(n["valor_total"], 2))
        por_dia_valor[chave].append(n)
    for (data, valor), notas_par in por_dia_valor.items():
        if len(notas_par) < 2:
            continue
        cpfs = {n.get("remetente_cpf") for n in notas_par} | {n.get("destinatario_cpf") for n in notas_par}
        posicoes = {n.get("posicao") for n in notas_par}
        if "REMETENTE" in posicoes and "DESTINATARIO" in posicoes and ADELA_CPF in cpfs:
            contraparte = next((c for c in cpfs if c and c != ADELA_CPF), None)
            alertas.append({
                "tipo": "CARROSSEL_IDA_VOLTA",
                "criticidade": "ALTA",
                "data": data,
                "valor": valor,
                "contraparte_cpf": contraparte,
                "notas": [n["numero"] for n in notas_par],
                "evidencia": f"Mesmo dia, mesmo valor (R$ {valor:,.2f}), operacao ida-e-volta com {contraparte}",
            })

    # 2. DEVOLUCAO AMPLIFICADA: A vende para B, B "vende" depois para A com >150% das cabecas
    vendas_de_adela = [n for n in notas if n.get("posicao") == "REMETENTE" and "VENDA" in n.get("natureza", "")]
    compras_de_adela = [n for n in notas if n.get("posicao") == "DESTINATARIO" and "VENDA" in n.get("natureza", "")]
    for venda in vendas_de_adela:
        for compra in compras_de_adela:
            if venda.get("destinatario_cpf") != compra.get("remetente_cpf"):
                continue
            dt_v = datetime.fromisoformat(venda["data"])
            dt_c = datetime.fromisoformat(compra["data"])
            dias = (dt_c - dt_v).days
            if dias <= 0 or dias > 180:
                continue
            cab_v = venda.get("cabecas", 0)
            cab_c = compra.get("cabecas", 0)
            if cab_v == 0:
                continue
            ratio = cab_c / cab_v
            if ratio >= 1.5:
                alertas.append({
                    "tipo": "DEVOLUCAO_AMPLIFICADA",
                    "criticidade": "MEDIA-ALTA",
                    "venda_origem": venda["numero"],
                    "compra_retorno": compra["numero"],
                    "contraparte_cpf": venda["destinatario_cpf"],
                    "cabecas_vendidas": cab_v,
                    "cabecas_retornadas": cab_c,
                    "ratio_amplificacao": round(ratio, 2),
                    "dias_intervalo": dias,
                    "evidencia": f"ADELA vendeu {cab_v} para CPF {venda['destinatario_cpf']} em {venda['data']}; {dias} dias depois recebeu {cab_c} cab. ({ratio:.1f}x)",
                })

    # 3. TRANSFERENCIA inter-CPF (uso indevido da natureza)
    for n in notas:
        if "TRANSFERENCIA" not in n.get("natureza", "").upper():
            continue
        rem = n.get("remetente_cpf", "")
        dest = n.get("destinatario_cpf", "")
        if rem and dest and rem != dest:
            alertas.append({
                "tipo": "TRANSFERENCIA_INTER_CPF",
                "criticidade": "MEDIA",
                "nota": n["numero"],
                "rem_cpf": rem,
                "dest_cpf": dest,
                "valor": n["valor_total"],
                "evidencia": "Natureza TRANSFERENCIA so e valida entre estabelecimentos do mesmo titular; CPFs distintos sugerem reclassificacao para VENDA",
            })

    # 4. CPF com multiplas IEs (FORNECEDOR_FANTASMA enriquecido)
    cpf_para_ies = defaultdict(set)
    for n in notas:
        cpf = n.get("remetente_cpf") if n.get("posicao") == "DESTINATARIO" else n.get("destinatario_cpf")
        ie = n.get("ie_remetente", "")
        if cpf and ie and cpf != ADELA_CPF:
            cpf_para_ies[cpf].add(ie)
    for cpf, ies in cpf_para_ies.items():
        if len(ies) >= 2:
            alertas.append({
                "tipo": "CPF_MULTIPLAS_IES",
                "criticidade": "ALTA",
                "cpf": cpf,
                "ies": sorted(ies),
                "evidencia": f"CPF {cpf} aparece com {len(ies)} IEs distintas: {sorted(ies)}",
            })

    return {"total_alertas": len(alertas), "alertas": alertas}


def login() -> str:
    resp = requests.post(
        f"{API_BASE}/auth/login",
        data={"username": EMAIL, "password": SENHA},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def auditar(token: str, payload: dict) -> dict:
    resp = requests.post(
        f"{API_BASE}/auditoria/nfae",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
        timeout=120,
    )
    if resp.status_code != 200:
        print(f"Erro {resp.status_code}: {resp.text[:500]}")
        resp.raise_for_status()
    return resp.json()


def main():
    print("[1/4] Login...")
    token = login()
    print("      OK")

    print("[2/4] Montando payload v2 (com CFOP + IE)...")
    payload = montar_payload()
    print(f"      OK - {len(payload['notas'])} notas (CFOP + IE preenchidos)")

    print("[3/4] Pipeline OrgAudi (RE-1 -> XGBoost -> F1-F6 -> A-07 -> A-08)...")
    resultado = auditar(token, payload)

    print("[4/4] Deteccao customizada complementar...")
    customizado = deteccao_customizada(payload["notas"])
    resultado["deteccao_customizada"] = customizado

    saida = Path("reports_nfa") / f"laudo_adela_v2_{datetime.now():%Y%m%d_%H%M%S}.json"
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8")

    aa = resultado.get("analise_assurance", {})
    print()
    print("=" * 70)
    print("RESULTADO PIPELINE (A-07)")
    print("=" * 70)
    print(f"Score:           {aa.get('score_risco')}")
    print(f"Probabilidade:   {aa.get('probabilidade_fraude')}")
    print(f"Criticidade:     {aa.get('criticidade')}")
    print(f"Padroes A-07:    {aa.get('padroes_detectados')}")
    print()
    print("=" * 70)
    print(f"DETECCAO CUSTOMIZADA ({customizado['total_alertas']} alertas)")
    print("=" * 70)
    for a in customizado["alertas"]:
        print(f"\n[{a['tipo']}] (criticidade: {a['criticidade']})")
        print(f"  {a['evidencia']}")
        for k, v in a.items():
            if k not in ("tipo", "criticidade", "evidencia"):
                print(f"  {k}: {v}")

    print(f"\nLaudo salvo em: {saida}")
    return resultado


if __name__ == "__main__":
    try:
        main()
    except requests.HTTPError as exc:
        print(f"Falha HTTP: {exc}", file=sys.stderr)
        sys.exit(1)
