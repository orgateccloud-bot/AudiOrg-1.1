"""Gate estrito para horizon_blue_one/core/ — chamado em CI e pre-push.

Rodar:
    python scripts/lint_core_strict.py

Falha (exit≠0) se:
    - ruff check horizon_blue_one/core/ tiver violações (config em core/ruff.toml)
    - mypy horizon_blue_one/core/ tiver erros (config em pyproject.toml)

Justificativa: o core/ concentra orchestrator, model_adapter e token_router
— módulos cujas regressões afetam todos os agentes. Linting mais rigoroso
aqui paga em estabilidade.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).parent.parent
ALVO = "horizon_blue_one/core/"


def _run(cmd: list[str]) -> int:
    print(f"\n==> {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=RAIZ, check=False)
    return proc.returncode


def main() -> int:
    falhas = 0

    # 1) Ruff estrito (categorias extras definidas em core/ruff.toml)
    rc = _run([sys.executable, "-m", "ruff", "check", ALVO])
    if rc != 0:
        falhas += 1
        print("[FAIL] ruff falhou em core/")
    else:
        print("[OK] ruff OK em core/")

    # 2) mypy estrito (overrides em pyproject.toml para core/)
    rc = _run([sys.executable, "-m", "mypy", ALVO, "--no-incremental"])
    if rc != 0:
        falhas += 1
        print("[FAIL] mypy falhou em core/")
    else:
        print("[OK] mypy OK em core/")

    if falhas:
        print(f"\n[REPROVADO] Gate estrito reprovou ({falhas} ferramentas com erro)")
        return 1
    print("\n[APROVADO] Gate estrito aprovado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
