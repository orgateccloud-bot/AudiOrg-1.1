"""A-27 @Epsilon — Forensic Intelligence & Relationship Mining
Mindset: "Follow the money"

Analisa grafos de transações para detectar:
- Triangulação fiscal (ciclos no grafo remetente→destinatário)
- Fragmentação (smurfing — muitas arestas de baixo valor)
- Conluio por centralidade de betweenness
"""
import json
from pydantic import BaseModel, Field
from horizon_blue_one.agents.base_agent import BaseAgent, AgentResult
from horizon_blue_one.core.model_adapter import call_model, ModelType


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

    # Score de conluio: ciclos indicam triangulação, alta centralidade indica nó pivô
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

        G, metricas = _build_graph(notas)

        if not metricas:
            # networkx não disponível ou notas vazias — análise degradada via LLM
            entidades = payload.get("entidades", [])
            prompt = f"Analise risco de conluio com {len(notas)} notas e entidades: {entidades[:20]}"
            metricas = {"nos": 0, "arestas": 0, "ciclos_detectados": 0, "score_conluio": 0.0}
        else:
            prompt = (
                f"Grafo de {metricas['nos']} entidades e {metricas['arestas']} transações. "
                f"Ciclos detectados: {metricas['ciclos_detectados']}. "
                f"Score de conluio (0-1): {metricas['score_conluio']}. "
                f"Entidades mais centrais: {metricas['entidades_suspeitas']}. "
                f"Interprete o risco fiscal e recomende ações."
            )

        resp = await call_model(ModelType.SONNET, prompt, SYSTEM)

        try:
            analise = json.loads(resp)
        except json.JSONDecodeError:
            analise = {
                "conclusao": resp[:500],
                "risco_conluio": "ALTO" if metricas.get("ciclos_detectados", 0) > 0 else "MÉDIO",
                "acoes_recomendadas": ["Verificar ciclos de transações", "Cruzar dados SEFAZ-GO"],
                "confianca": 0.75,
            }

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
            confidence=analise.get("confianca", 0.85),
        )
