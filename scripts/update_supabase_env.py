"""
Lê uma chave do clipboard (Windows) e atualiza UMA variável no config.env.

Uso (interativo):
    python scripts/update_supabase_env.py SUPABASE_ANON_KEY
    python scripts/update_supabase_env.py SUPABASE_SERVICE_KEY
    python scripts/update_supabase_env.py SUPABASE_JWT_SECRET

Fluxo:
    1. Antes de rodar, clique em "Copy" no Supabase para a chave certa
    2. Roda este script com o NOME da var como argumento
    3. Ele lê o clipboard, valida prefixo, atualiza config.env in-place
    4. Não imprime o valor da chave em momento algum
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / "config.env"


def _ler_clipboard() -> str:
    """Lê clipboard via PowerShell (Windows)."""
    out = subprocess.check_output(
        ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
        text=True, encoding="utf-8",
    )
    return out.strip()


PREFIXOS = {
    "SUPABASE_ANON_KEY": "sb_publishable_",
    "SUPABASE_SERVICE_KEY": "sb_secret_",
    "SUPABASE_JWT_SECRET": None,  # base64 ou texto livre — sem prefixo fixo
    "SUPABASE_URL": "https://",
    "ANTHROPIC_API_KEY": "sk-ant-",
}


def main(var: str) -> int:
    if var not in PREFIXOS:
        print(f"ERRO: variável '{var}' não conhecida. Use uma de: {list(PREFIXOS)}")
        return 2

    if not ENV.exists():
        print(f"ERRO: {ENV} não existe.")
        return 2

    valor = _ler_clipboard()
    if not valor:
        print("ERRO: clipboard vazio. Clique em 'Copy' no Supabase antes de rodar.")
        return 2

    prefixo = PREFIXOS[var]
    if prefixo and not valor.startswith(prefixo):
        print(f"ERRO: clipboard não começa com '{prefixo}' — confira o que copiou.")
        print(f"      (recebeu {len(valor)} chars começando em '{valor[:8]}…')")
        return 2

    # Linha-a-linha — preserva comentários/encoding
    linhas = ENV.read_text(encoding="utf-8").splitlines(keepends=True)
    pattern = re.compile(rf"^\s*{re.escape(var)}\s*=.*$")
    achou = False
    for i, linha in enumerate(linhas):
        if pattern.match(linha.rstrip("\r\n")) and not linha.lstrip().startswith("#"):
            terminator = "\r\n" if linha.endswith("\r\n") else "\n"
            linhas[i] = f"{var}={valor}{terminator}"
            achou = True
            break

    if not achou:
        # Adiciona ao final
        linhas.append(f"\n{var}={valor}\n")

    ENV.write_text("".join(linhas), encoding="utf-8")
    print(f"[OK] {var} atualizado em {ENV.name} ({len(valor)} chars).")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    sys.exit(main(sys.argv[1]))
