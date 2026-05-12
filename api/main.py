"""OrgAudi Sovereign API v8.0 — Motor unificado com 4 módulos."""
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path


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

from api.middleware import claude_metrics as _claude_metrics  # noqa: F401  — registra listener no import
from api.middleware.body_size_limit import BodySizeLimitMiddleware
from api.middleware.prometheus import PrometheusMiddleware
from api.middleware.rate_limit import RateLimitMiddleware
from api.middleware.security_headers import SecurityHeadersMiddleware
from api.observability import orgaudi_metrics as _orgaudi_metrics  # noqa: F401  — registra listener + counters orgaudi_*
from api.observability.sentry_init import init_sentry
from api.routes import agente, auditoria, auth, clientes
from nfa_extractor.infrastructure.database_v2 import Base, engine

logger = logging.getLogger("orgaudi")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_sentry()  # #25: no-op se SENTRY_DSN ausente; warn se ENVIRONMENT=production sem DSN
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

# Origens permitidas: dev local + lista de ALLOWED_ORIGINS (CSV) em produção
_origens_dev = [
    "http://localhost:5173", "http://localhost:5174", "http://localhost:5175",
    "http://127.0.0.1:5173", "http://127.0.0.1:5174", "http://127.0.0.1:5175",
]
_origens_prod = [
    o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()
]
_ambiente = os.environ.get("ENVIRONMENT", "development").lower()
_em_producao = _ambiente == "production"

app.add_middleware(
    SecurityHeadersMiddleware,
    enable_hsts=_em_producao,
)
app.add_middleware(
    BodySizeLimitMiddleware,
    max_body_size=int(os.environ.get("MAX_BODY_SIZE_MB", "10")) * 1024 * 1024,
)
app.add_middleware(RateLimitMiddleware, rate=60, window=60)
app.add_middleware(PrometheusMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origens_prod if _em_producao else _origens_dev,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
    max_age=600,
)

app.include_router(auth.router)
app.include_router(auditoria.router)
app.include_router(clientes.router)
app.include_router(agente.router)

try:
    from api.routes import finance, metrics, nfa_ai_parser
    app.include_router(metrics.router)
    app.include_router(finance.router)
    app.include_router(nfa_ai_parser.router)
except ImportError as exc:
    logger.warning("routers_opcionais_indisponiveis", modulo=str(exc))
except Exception as exc:
    logger.error("erro_carregando_routers_opcionais", error=str(exc))


@app.get("/ping")
async def ping():
    return {"status": "ok", "message": "pong", "version": "8.0.0"}


@app.get("/stats")
def get_stats():
    from api.services.auditoria_nfae import obter_stats_nfae
    from nfa_extractor.infrastructure.database_v2 import Cliente, Laudo, SessionLocal
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
    """Relatório de uso e custo de tokens Claude por modelo."""
    from horizon_blue_one.agents.a_token import relatorio_custo
    return await relatorio_custo()


@app.get("/")
def root():
    return {"status": "OrgAudi Sovereign Shield Active", "modulos": [
        "horizon_blue_one", "pdf_engine", "nfa_extractor", "api"
    ]}
