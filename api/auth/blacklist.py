"""
ORGATEC – Blacklist de JWT (revogação por logout).

Mantém um set in-memory de `jti` (JWT IDs) ou hashes de tokens revogados.
Para produção multi-instance, substituir por Redis com TTL = exp do token.

API:
- adicionar(token_hash, expira_em_ts)  — revoga
- esta_revogado(token_hash) -> bool    — verifica
- limpar_expirados()                   — purge automático ao adicionar
"""
from __future__ import annotations

import hashlib
import time

# Map[hash_token] = expira_em_unix_ts
_REVOGADOS: dict[str, float] = {}


def _hash_token(token: str) -> str:
    """SHA-256 do token (evita guardar token bruto em memória)."""
    return hashlib.sha256(token.encode()).hexdigest()


def adicionar(token: str, expira_em_ts: float) -> None:
    """Revoga `token` até `expira_em_ts` (unix timestamp)."""
    _limpar_expirados()
    _REVOGADOS[_hash_token(token)] = expira_em_ts


def esta_revogado(token: str) -> bool:
    """Retorna True se `token` foi revogado e ainda não expirou."""
    h = _hash_token(token)
    exp = _REVOGADOS.get(h)
    if exp is None:
        return False
    if exp < time.time():
        # Já expirou — remove e considera não revogado (JWT exp já barra)
        _REVOGADOS.pop(h, None)
        return False
    return True


def _limpar_expirados() -> None:
    """Remove entradas com TTL vencido. Chamado em writes."""
    agora = time.time()
    expirados = [h for h, exp in _REVOGADOS.items() if exp < agora]
    for h in expirados:
        _REVOGADOS.pop(h, None)


def _limpar_tudo() -> None:
    """Reset total — apenas para testes."""
    _REVOGADOS.clear()
