"""
Verifica se as 4 tabelas (profiles, categories, transactions, predictions)
estão presentes no Supabase usando o SERVICE_KEY do config.env.

Uso:
    python supabase/check_schema.py

Saída esperada (após aplicar 0001_finance_schema.sql):
    [OK] profiles      — acessível
    [OK] categories    — acessível
    [OK] transactions  — acessível
    [OK] predictions   — acessível
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Carrega config.env como env vars
ROOT = Path(__file__).resolve().parent.parent
for nome in ("config.env", ".env"):
    p = ROOT / nome
    if not p.exists():
        continue
    for linha in p.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, _, valor = linha.partition("=")
        chave, valor = chave.strip(), valor.strip().strip('"').strip("'")
        if chave and chave not in os.environ:
            os.environ[chave] = valor
    break

from supabase import create_client  # noqa: E402

url = os.getenv("SUPABASE_URL", "")
key = os.getenv("SUPABASE_SERVICE_KEY", "")

if not url or not key:
    print("ERRO: SUPABASE_URL ou SUPABASE_SERVICE_KEY ausentes no config.env")
    sys.exit(1)

print(f"Conectando em {url} ...")
client = create_client(url, key)

TABELAS = ["profiles", "categories", "transactions", "predictions"]
faltando: list[str] = []

for t in TABELAS:
    try:
        # head=True só pede o COUNT, não retorna linhas
        client.table(t).select("id", count="exact", head=True).execute()
        print(f"  [OK] {t:<14} — acessível")
    except Exception as e:
        msg = str(e).splitlines()[0][:120]
        print(f"  [--] {t:<14} — {msg}")
        faltando.append(t)

print()
if not faltando:
    print(">> Schema OK — todas as 4 tabelas presentes.")
    sys.exit(0)
else:
    print(f">> {len(faltando)} tabela(s) ausente(s): {', '.join(faltando)}")
    print(">> Aplique supabase/migrations/0001_finance_schema.sql no Supabase Studio")
    print("   Studio -> SQL Editor -> cole o arquivo -> Run")
    sys.exit(2)
