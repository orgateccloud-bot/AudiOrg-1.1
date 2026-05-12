"""Configuração — OrgAudi Sovereign / HORIZON-BLUE ONE.

Lê credenciais em cascata:
1. Variáveis de ambiente (os.getenv)
2. config.env (formato KEY=VALUE)
3. .env na raiz do projeto
Motor único: Anthropic Claude.
"""
import os
from pathlib import Path


def _ler_arquivo_env(caminho: Path) -> dict[str, str]:
    resultado: dict[str, str] = {}
    if caminho.exists():
        with caminho.open(encoding="utf-8") as f:
            for raw in f:
                linha = raw.strip()
                if linha and "=" in linha and not linha.startswith("#"):
                    k, v = linha.split("=", 1)
                    resultado[k.strip()] = v.strip()
    return resultado


def _obter(chave: str, padrao: str = "") -> str:
    val = os.getenv(chave)
    if val:
        return val
    _raiz = Path(__file__).parent.parent.parent
    for nome in ("config.env", ".env"):
        dados = _ler_arquivo_env(_raiz / nome)
        if chave in dados:
            return dados[chave]
    return padrao


class Settings:
    # ─── Anthropic Claude (único motor) ─────────────────────────────────────
    ANTHROPIC_API_KEY: str
    CLAUDE_MODEL_ID: str   # Sonnet 4.6
    HAIKU_MODEL_ID: str    # Haiku 4.5
    OPUS_MODEL_ID: str     # Opus 4.7

    # ─── JWT ────────────────────────────────────────────────────────────────
    JWT_SECRET: str
    JWT_ALGORITHM: str
    JWT_EXPIRE_MINUTES: int

    # ─── App ────────────────────────────────────────────────────────────────
    APP_ENV: str
    APP_PORT: int
    LOG_LEVEL: str

    # ─── Supabase (opcional) ────────────────────────────────────────────────
    SUPABASE_URL: str
    SUPABASE_SERVICE_KEY: str
    SUPABASE_ANON_KEY: str

    # ─── Auditoria ──────────────────────────────────────────────────────────
    AUDIT_HASH_LEN: int

    # ─── LSTM (opcional) ────────────────────────────────────────────────────
    LSTM_MODEL_PATH: str       # path para .pt treinado; vazio = modo heurístico

    # ─── MCP (opcional) ─────────────────────────────────────────────────────
    MCP_FETCH_ALLOWLIST: str   # domínios extras separados por vírgula
    ORGAUDI_DB_PATH: str       # path customizado para orgatec_sovereign.db

    def __init__(self) -> None:
        self.ANTHROPIC_API_KEY = _obter("ANTHROPIC_API_KEY")
        self.CLAUDE_MODEL_ID   = _obter("CLAUDE_MODEL_ID", "claude-sonnet-4-6")
        self.HAIKU_MODEL_ID    = _obter("HAIKU_MODEL_ID",  "claude-haiku-4-5-20251001")
        self.OPUS_MODEL_ID     = _obter("OPUS_MODEL_ID",   "claude-opus-4-7")

        self.JWT_SECRET         = _obter("JWT_SECRET", "nfa-extractor-dev-secret-orgatec-2026!!")
        self.JWT_ALGORITHM      = _obter("JWT_ALGORITHM", "HS256")
        self.JWT_EXPIRE_MINUTES = int(_obter("JWT_EXPIRE_MINUTES", "60"))

        self.APP_ENV   = _obter("APP_ENV", "development")
        self.APP_PORT  = int(_obter("APP_PORT", "8081"))
        self.LOG_LEVEL = _obter("LOG_LEVEL", "INFO")

        self.SUPABASE_URL         = _obter("SUPABASE_URL")
        self.SUPABASE_SERVICE_KEY = _obter("SUPABASE_SERVICE_KEY")
        self.SUPABASE_ANON_KEY    = _obter("SUPABASE_ANON_KEY")

        try:
            self.AUDIT_HASH_LEN = int(_obter("AUDIT_HASH_LEN", "64"))
        except ValueError:
            self.AUDIT_HASH_LEN = 64

        self.LSTM_MODEL_PATH     = _obter("LSTM_MODEL_PATH", "")
        self.MCP_FETCH_ALLOWLIST = _obter("MCP_FETCH_ALLOWLIST", "")
        self.ORGAUDI_DB_PATH     = _obter("ORGAUDI_DB_PATH", "")

    @property
    def dev_bypass_habilitado(self) -> bool:
        return self.APP_ENV.lower() != "production"


settings = Settings()
