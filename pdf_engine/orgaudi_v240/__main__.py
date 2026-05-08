"""
orgaudi.__main__
════════════════
Entry point para `python -m orgaudi`. Apenas redireciona para o CLI principal.
"""
import sys

from .cli import main


if __name__ == "__main__":
    sys.exit(main())
