"""OrgAudi Sovereign API v8.0 — Motor unificado com 4 módulos."""
import os
from contextlib import asynccontextmanager
from pathlib import Path
import logging


def _carregar_env_local() -> None:
    """Carrega config.env (ou .env) na raiz do projeto em os.environ.
    Variáveis já existentes no ambiente NÃO são sobrescritas."""
    base = Path(__file__).resolve().parent.parent
    for nome in ("config.env", ".env"):
        caminho = base / nome
        if not caminho.exists():
            continue
        for linha in caminho.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            chave, _, valor = linha.partition("=")
            chave, valor = chave.strip(), valor.strip().strip('"').strip("'")
            if chave and chave not in os.environ:
                os.environ[chave] = valor
        break  # carrega apenas o primeiro encontrado


_carregar_env_local()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.middleware.rate_limit import RateLimitMiddleware
from api.routes import auditoria, auth, batch, chat, clientes, agente
from nfa_extractor.infrastructure.database_v2 import Base, engine

logger = logging.getLogger("orgaudi")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    logger.info("OrgAudi iniciado — banco sincronizado")
    yield
    logger.info("OrgAudi encerrado")


app = FastAPI(
    title="OrgAudi Sovereign API",
    version="8.0.0",
    description="Motor unificado: Horizon-Blue-One | PDF Engine | NFA Extractor | Worktree",
    lifespan=lifespan,
)

def _get_allowed_origins() -> list[str]:
    """Origens CORS via env var ALLOWED_ORIGINS (CSV).

    Sem env var, mantém os defaults de dev (localhost:5173-5175) para não
    quebrar o setup local de desenvolvimento.
    """
    bruto = os.getenv("ALLOWED_ORIGINS", "").strip()
    if not bruto:
        return [
            "http://localhost:5173", "http://localhost:5174", "http://localhost:5175",
            "http://127.0.0.1:5173", "http://127.0.0.1:5174", "http://127.0.0.1:5175",
        ]
    return [origem.strip() for origem in bruto.split(",") if origem.strip()]


app.add_middleware(RateLimitMiddleware, rate=60, window=60)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(auditoria.router)
app.include_router(clientes.router)
app.include_router(agente.router)
app.include_router(chat.router)
app.include_router(batch.router)

# Routers opcionais — carregados individualmente para que falha em um
# não derrube os demais.
for _nome in ("metrics", "nfa_ai_parser"):
    try:
        _mod = __import__(f"api.routes.{_nome}", fromlist=["router"])
        app.include_router(_mod.router)
    except Exception as _exc:
        logger.warning(
            "router_opcional_indisponivel",
            extra={"router": _nome, "erro": str(_exc), "tipo_erro": type(_exc).__name__},
        )


@app.get("/ping")
async def ping():
    return {"status": "ok", "message": "pong", "version": "8.0.0"}


@app.get("/stats")
def get_stats():
    from api.services.auditoria_nfae import obter_stats_nfae
    from nfa_extractor.infrastructure.database_v2 import SessionLocal, Cliente, Laudo
    db = SessionLocal()
    try:
        stats = obter_stats_nfae()
        return {
            "total_clientes":          db.query(Cliente).count(),
            "total_laudos":            db.query(Laudo).count(),
            "total_auditorias_nfae":   stats["total_auditorias_nfae"],
            "total_notas_processadas": stats["total_notas_processadas"],
            "score_medio":             stats["score_medio_nfae"],
        }
    finally:
        db.close()


@app.get("/tokens")
async def get_token_stats():
    """Relatório de uso e custo de tokens — agente foi arquivado em cleanup.

    Retorna status indicando que o agente de tokens foi arquivado.
    """
    return {"status": "token_agent_archived", "detail": "a_token agente foi arquivado"}


@app.get("/")
def root():
    return {"status": "OrgAudi Sovereign Shield Active", "modulos": [
        "horizon_blue_one", "pdf_engine", "nfa_extractor", "api"
    ]}
