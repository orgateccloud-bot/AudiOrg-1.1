import pandas as pd

from nfa_extractor.domain.extractor import NFA, resumo_geral


def processar_para_dataframe(notas: list[NFA]) -> pd.DataFrame:
    """Converte lista de NFAs em um DataFrame limpo."""
    if not notas:
        return pd.DataFrame()
        
    data = []
    for n in notas:
        data.append({
            "NFA": n.numero,
            "Data": n.emissao,
            "Natureza": n.natureza,
            "Destinatario": n.destinatario.nome if n.destinatario else "N/I",
            "CPF/CNPJ": n.destinatario.cpf_cnpj if n.destinatario else "N/I",
            "Municipio": n.destinatario.municipio if n.destinatario else "N/I",
            "Qtd": n.quantidade_total,
            "Valor": n.valor_total,
            "ICMS": n.valor_icms
        })
    
    df = pd.DataFrame(data)
    if not df.empty:
        df['Data'] = pd.to_datetime(df['Data'], errors='coerce')
        
        # Detecção de Anomalias (Preço muito acima/abaixo da média por Natureza)
        df['Ticket_Item'] = df['Valor'] / df['Qtd'].replace(0, 1)
        media_cat = df.groupby('Natureza')['Ticket_Item'].transform('mean')
        std_cat = df.groupby('Natureza')['Ticket_Item'].transform('std').fillna(0)
        
        # Marca como anomalia se fugir mais de 2 desvios padrão
        df['Anomalia'] = (abs(df['Ticket_Item'] - media_cat) > (std_cat * 1.5)) & (std_cat > 0)
        
    return df

def get_dashboard_metrics(notas: list[NFA]):
    """Retorna dicionário de métricas consolidadas."""
    res = resumo_geral(notas)
    return {
        "total_notas": res['total_notas'],
        "total_valor": res['total_valor'],
        "total_cabecas": res['total_cabecas'],
        "ticket_medio": res['ticket_medio'],
        "por_mes": res['por_mes'],
        "por_categoria": res['por_categoria']
    }
