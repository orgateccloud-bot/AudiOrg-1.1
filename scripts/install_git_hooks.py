"""Instala hooks Git locais para OrgAudi.

Rodar uma vez por checkout:
    python scripts/install_git_hooks.py

Instala:
    .git/hooks/pre-push → roda scripts/lint_core_strict.py + pytest -q
"""
from __future__ import annotations

import stat
import sys
from pathlib import Path

RAIZ = Path(__file__).parent.parent
HOOKS_DIR = RAIZ / ".git" / "hooks"

PRE_PUSH = r"""#!/usr/bin/env bash
# Hook gerado por scripts/install_git_hooks.py — NÃO editar à mão.
# Bloqueia push se o gate estrito de core/ ou os testes falharem.
set -e
echo "[pre-push] gate estrito em horizon_blue_one/core/..."
python scripts/lint_core_strict.py
echo "[pre-push] pytest -q..."
python -m pytest -q --no-header
echo "[pre-push] OK"
"""


def main() -> int:
    if not HOOKS_DIR.exists():
        print(f"[ERRO] {HOOKS_DIR} não existe — este checkout não é um repo Git?")
        return 1
    alvo = HOOKS_DIR / "pre-push"
    alvo.write_text(PRE_PUSH, encoding="utf-8", newline="\n")
    # chmod +x (no-op no Windows mas inofensivo)
    alvo.chmod(alvo.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    print(f"[OK] pre-push instalado em {alvo}")
    print("     Para pular um push (emergência): git push --no-verify")
    return 0


if __name__ == "__main__":
    sys.exit(main())
