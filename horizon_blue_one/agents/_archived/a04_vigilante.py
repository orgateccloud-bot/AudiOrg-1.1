"""A-04 @Vigilante — Monitoramento de Padrões Suspeitos e Anti-Fraude Comportamental"""
import json
from collections import Counter
from datetime import datetime
from horizon_blue_one.agents.base_agent import BaseAgent, AgentResult
from horizon_blue_one.core.model_adapter import call_model, ModelType
from horizon_blue_one.orgaudi.anomalias import CATALOGO, listar_criticos

SYSTEM = """Você é o @Vigilante da ORGATEC IA, especialista em detecção comportamental de fraude fiscal.
Analise padrões temporais, concentração de destinatários, frequência de operações e tipologias AN-01..AN-18.
Retorne JSON: {"tipologias_detectadas": ["AN-01",...], "nivel_alerta": "VERDE|AMARELO|VERMELHO", "narrativa": "...", "score_fraude": 0.0}"""

DIAS_SUSPEITOS = {5, 6}  # sábado=5, domingo=6


class VigilanteAgent(BaseAgent):
    agent_id = "A-04"
    name = "@Vigilante"

    async def process(self, payload: dict) -> AgentResult:
        notas = payload.get("notas", [])
        self.log("Monitorando padrões suspeitos", total_notas=len(notas))

        alertas_pre = []
        # AN-10: Períodos suspeitos
        for n in notas:
            try:
                data_str = n.get("data", "")
                if data_str:
                    dt = datetime.fromisoformat(data_str)
                    if dt.weekday() in DIAS_SUSPEITOS:
                        alertas_pre.append("AN-10")
                        break
            except ValueError:
                pass

        # AN-13: Concentração atípica
        destinos = [n.get("destinatario_cpf", "") for n in notas if n.get("destinatario_cpf")]
        if destinos:
            cnt = Counter(destinos)
            top_pct = cnt.most_common(1)[0][1] / len(destinos)
            if top_pct > 0.80:
                alertas_pre.append("AN-13")

        # AN-18: Ausência GTA
        notas_animais = [n for n in notas if any(a in str(n.get("atividade", "")).lower()
                         for a in ["bovino", "suíno", "equino", "caprino", "ovino"])]
        if notas_animais and not any(n.get("gta_numero") for n in notas_animais):
            alertas_pre.append("AN-18")

        criticos_info = {c.codigo: c.nome for c in listar_criticos()}
        prompt = f"""Analise os padrões das {len(notas)} notas para tipologias AN-01..AN-18.
Tipologias pré-detectadas: {list(set(alertas_pre))}
Catálogo CRÍTICO disponível: {criticos_info}
Dados resumidos: destinatários únicos={len(set(destinos))}, total_notas={len(notas)}"""

        resp = await call_model(ModelType.CLAUDE, prompt, SYSTEM, max_tokens=2048)
        try:
            data = json.loads(resp)
        except json.JSONDecodeError:
            nivel = "VERMELHO" if alertas_pre else "VERDE"
            data = {"tipologias_detectadas": list(set(alertas_pre)), "nivel_alerta": nivel,
                    "narrativa": "Análise preliminar via regras locais.", "score_fraude": len(alertas_pre) * 0.15}

        status = "ESCALADO" if data.get("nivel_alerta") == "VERMELHO" else "APROVADO"
        return AgentResult(
            agent_id=self.agent_id,
            status=status,
            output=data,
            confidence=0.88,
        )
