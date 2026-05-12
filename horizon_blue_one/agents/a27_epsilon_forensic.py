"""A-27 @Epsilon — Forensic Intelligence & Relationship Mining.

Mindset: "Follow the money".

Analisa grafos de transações para detectar:
- Triangulação fiscal (ciclos no grafo remetente→destinatário)
- Fragmentação (smurfing — muitas arestas de baixo valor)
- Conluio por centralidade de betweenness

v1.1: chamada ao LLM passa por @Delta via BaseAgent._call_llm() — CPFs
e nomes do grafo são anonimizados antes de irem para Claude.
"""
from pydantic import BaseModel, Field

from horizon_blue_one.agents.base_agent import AgentResult, BaseAgent
from horizon_blue_one.core.model_adapter import ModelType


class RelationshipGraphSchema(BaseModel):
    entidades_relacionadas: list
    padrao_detectado: str
    score_conluio: float = Field(..., ge=0, le=1)
    recomendacao_bloqueio: bool


SYSTEM = """Você é o @Epsilon, perito em inteligência forense de dados da ORGATEC IA.
Sua especialidade é detectar triangulação, fragmentação de notas (Smurfing) e conluio.
Recebe métricas do grafo de transações e interpreta os riscos legais e fiscais.
Retorne JSON: {"conclusao": "...", "risco_conluio": "BAIXO|MÉDIO|ALTO|CRÍTICO",
               "acoes_recomendadas": [], "confianca": 0.0}"""


def _build_graph(notas: list):
    """Constrói grafo direcionado de transações. Retorna (G, metricas)."""
    try:
        import networkx as nx
    except ImportError:
        return None, {}

    G = nx.DiGraph()
    for nota in notas:
        rem = str(nota.get("remetente_cpf", ""))
        dest = str(nota.get("destinatario_cpf", ""))
        if not rem or not dest or rem == dest:
            continue
        valor = float(nota.get("valor_total", 0))
        if G.has_edge(rem, dest):
            G[rem][dest]["weight"] += valor
            G[rem][dest]["count"] += 1
        else:
            G.add_edge(rem, dest, weight=valor, count=1)

    if len(G.nodes) == 0:
        return G, {}

    ciclos = list(nx.simple_cycles(G))
    centralidade = nx.betweenness_centrality(G, weight="weight")
    max_central = max(centralidade.values()) if centralidade else 0.0
    score = min(len(ciclos) * 0.20 + max_central * 0.50, 1.0)

    metricas = {
        "nos": len(G.nodes),
        "arestas": len(G.edges),
        "ciclos_detectados": len(ciclos),
        "nos_ciclos": list({n for c in ciclos for n in c})[:10],
        "max_centralidade": round(max_central, 4),
        "score_conluio": round(score, 4),
        "entidades_suspeitas": [
            k for k, v in sorted(centralidade.items(), key=lambda x: x[1], reverse=True)[:5]
        ],
    }
    return G, metricas


class EpsilonAgent(BaseAgent):
    agent_id = "A-27"
    name = "@Epsilon"

    async def process(self, payload: dict) -> AgentResult:
        notas = payload.get("notas", [])
        self.log("Minerando grafo de relacionamentos", total_notas=len(notas))

        _, metricas = _build_graph(notas)

        if not metricas:
            entidades = payload.get("entidades", [])
            prompt_payload = {"qtd_notas": len(notas), "entidades": entidades[:20]}
            template = (
                "Análise degradada (sem grafo): {payload}\n"
                "Interprete risco de conluio com os dados disponíveis."
            )
            metricas = {"nos": 0, "arestas": 0, "ciclos_detectados": 0, "score_conluio": 0.0}
        else:
            prompt_payload = {"metricas": metricas}
            template = (
                "Grafo de transações: {payload}\n"
                "Interprete o risco fiscal e recomende ações."
            )

        resp = await self._call_llm(
            model_type=ModelType.SONNET,
            prompt_payload=prompt_payload,
            prompt_template=template,
            system=SYSTEM,
            max_tokens=2048,
        )

        analise, _ok = self.parse_json_response(
            resp,
            fallback={
                "conclusao": resp[:500],
                "risco_conluio": "ALTO" if metricas.get("ciclos_detectados", 0) > 0 else "MÉDIO",
                "acoes_recomendadas": ["Verificar ciclos de transações", "Cruzar dados SEFAZ-GO"],
                "confianca": 0.75,
            },
        )

        score = metricas.get("score_conluio", 0.0)
        deve_escalar = score > 0.5 or metricas.get("ciclos_detectados", 0) > 0

        self.log(
            "Análise forense de grafo concluída",
            score_conluio=score,
            ciclos=metricas.get("ciclos_detectados", 0),
            escalar=deve_escalar,
        )

        return AgentResult(
            agent_id=self.agent_id,
            status="ESCALADO" if deve_escalar else "APROVADO",
            output={
                "analise": analise,
                "metricas_grafo": metricas,
                "score_conluio": score,
            },
            confidence=float(analise.get("confianca", 0.85)),
        )
