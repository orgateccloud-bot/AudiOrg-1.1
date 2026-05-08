"""Regra Especial 1 — Reclassificação VENDA → COMPRA para produtor rural DESTINATÁRIO.

Aprovada: Robson Alain Veloso — CRC-GO | Warley Veloso — CTO
Base legal: NBC TG 16 (Estoques) + NBC TG 25 (Estimativas) + Lei 9.250/1995

NUNCA modificar sem aprovação do supervisor CRC-GO.
"""

ATIVIDADES_RURAIS = {
    "cria", "recria", "engorda", "criação", "agricultura",
    "bovino", "suíno", "ave", "caprino", "ovino",
    "equino", "piscicultura", "apicultura",
    "soja", "milho", "feijão", "cana", "café",
}


def aplicar_regra_especial_1(nota: dict) -> dict:
    """Aplica RE-1 se todos os critérios forem atendidos. Retorna nota com classificação."""
    natureza  = (nota.get("natureza", "") or "").upper()
    posicao   = (nota.get("posicao", "") or "").upper()
    atividade = (nota.get("atividade", "") or "").lower()
    tipo_doc  = (nota.get("tipo_doc", "nfa-e") or "").lower()
    valor     = float(nota.get("valor_total", 0))

    aplica = (
        "nfa" in tipo_doc
        and natureza == "VENDA"
        and "DESTIN" in posicao
        and any(a in atividade for a in ATIVIDADES_RURAIS)
    )

    alertas   = []
    confianca = 0.99

    if aplica:
        if valor > 500_000:
            alertas.append("ALERTA: valor > R$500k — revisão manual obrigatória")
            confianca = 0.75
        if valor < 100:
            alertas.append("ALERTA: valor < R$100 — suspeito de teste")
            confianca = 0.75

        nota.update({
            "natureza_exibicao": "COMPRA",
            "categoria_contabil": "DESPESA",
            "efeito_irpf": "SUBTRAI",
            "conta_debito":  "1.1.2.01",    # Gado em Rebanho
            "conta_credito": "2.1.1.1.01",  # Fornecedores
            "regra_aplicada": "REGRA_ESPECIAL_1",
            "confianca": confianca,
            "alertas_re1": alertas,
        })
    else:
        nota.update({
            "natureza_exibicao": natureza,
            "categoria_contabil": "RECEITA" if natureza == "VENDA" else natureza,
            "efeito_irpf": "SOMA" if natureza == "VENDA" else "NEUTRO",
            "regra_aplicada": "CLASSIFICACAO_NORMAL",
            "confianca": 0.99,
            "alertas_re1": [],
        })
    return nota
