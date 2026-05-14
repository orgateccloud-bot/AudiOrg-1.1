"""Configuração — OrgAudi Sovereign / HORIZON-BLUE ONE.
Lê credenciais em cascata:
1. Variáveis de ambiente (os.getenv)
2. config.env (formato KEY=VALUE)
3. .env na raiz do projeto
Motor único: Anthropic Claude.
Supabase: bfumcgchpwtbukahvbng (sa-east-1).
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path


def _ler_arquivo_env(caminho: Path) -> dict[str, str]:
    """Lê arquivo KEY=VALUE ignorando comentários e linhas vazias."""
    resultado: dict[str, str] = {}
    if caminho.exists():
        with open(caminho, "r", encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if linha and "=" in linha and not linha.startswith("#"):
                    k, v = linha.split("=", 1)
                    resultado[k.strip()] = v.strip()
    return resultado


def _obter(chave: str, padrao: str = "") -> str:
    """Lê variável de ambiente com fallback para config.env / .env."""
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
    """Configurações centralizadas do OrgAudi Sovereign."""

    # ─── Anthropic Claude (único motor LLM) ──────────────────────────────────
    ANTHROPIC_API_KEY: str
    CLAUDE_MODEL_ID: str   # Sonnet 4.6
    HAIKU_MODEL_ID: str    # Haiku 4.5
    OPUS_MODEL_ID: str     # Opus 4.7

    # ─── JWT ─────────────────────────────────────────────────────────────────
    JWT_SECRET: str
    JWT_ALGORITHM: str
    JWT_EXPIRE_MINUTES: int

    # ─── App ─────────────────────────────────────────────────────────────────
    APP_ENV: str
    APP_PORT: int
    LOG_LEVEL: str

    # ─── Auditoria ────────────────────────────────────────────────────────────
    AUDIT_HASH_LEN: int

    # ─── Supabase ────────────────────────────────────────────────────────────
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str
    SUPABASE_JWT_SECRET: str

    def __init__(self) -> None:
        # LLM
        self.ANTHROPIC_API_KEY = _obter("ANTHROPIC_API_KEY")
        self.CLAUDE_MODEL_ID = _obter("CLAUDE_MODEL_ID", "claude-sonnet-4-6")
        self.HAIKU_MODEL_ID = _obter("HAIKU_MODEL_ID", "claude-haiku-4-5-20251001")
        self.OPUS_MODEL_ID = _obter("OPUS_MODEL_ID", "claude-opus-4-7")

        # JWT — fallback gerado dinamicamente (não persistido, apenas para dev)
        _jwt_fallback = "nfa-extractor-dev-secret-orgatec-2026!!"
        self.JWT_SECRET = _obter("JWT_SECRET", _jwt_fallback)
        self.JWT_ALGORITHM = _obter("JWT_ALGORITHM", "HS256")
        self.JWT_EXPIRE_MINUTES = int(_obter("JWT_EXPIRE_MINUTES", "60"))

        # App
        self.APP_ENV = _obter("APP_ENV", "development")
        self.APP_PORT = int(_obter("APP_PORT", "8081"))
        self.LOG_LEVEL = _obter("LOG_LEVEL", "INFO")

        # Auditoria
        try:
            self.AUDIT_HASH_LEN = int(_obter("AUDIT_HASH_LEN", "64"))
        except ValueError:
            self.AUDIT_HASH_LEN = 64

        # Supabase
        self.SUPABASE_URL = _obter(
            "SUPABASE_URL", "https://bfumcgchpwtbukahvbng.supabase.co"
        )
        self.SUPABASE_ANON_KEY = _obter("SUPABASE_ANON_KEY", "")
        self.SUPABASE_SERVICE_ROLE_KEY = _obter("SUPABASE_SERVICE_ROLE_KEY", "")
        self.SUPABASE_JWT_SECRET = _obter("SUPABASE_JWT_SECRET", "")

    @property
    def dev_bypass_habilitado(self) -> bool:
        """True em ambientes não-produção (permite bypass de auth em testes)."""
        return self.APP_ENV.lower() != "production"

    @property
    def supabase_configurado(self) -> bool:
        """True se as credenciais Supabase foram injetadas via env/config."""
        return bool(self.SUPABASE_ANON_KEY and self.SUPABASE_URL)


settings = Settings()
