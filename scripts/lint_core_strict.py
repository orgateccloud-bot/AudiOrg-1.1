"""
Gate estrito para horizon_blue_one/core/.
Executado pelo hook pre-push. Falha com sys.exit(1) se alguma regra for violada.
"""
import re
import sys
from pathlib import Path

CORE_DIR = Path(__file__).parent.parent / "horizon_blue_one" / "core"

# Arquivos onde nomes de modelo hardcoded SÃO permitidos (tabela de preços, defaults de config)
PERMITIDO_MODELO_HARDCODE = {"claude_stats_writer.py", "config.py"}

# Padrão: instanciação direta do client Anthropic fora do model_adapter
PATRON_CLIENT_DIRETO = re.compile(r"anthropic\.Anthropic\s*\(")

# Padrão: imports legados que não devem mais existir
PATRON_IMPORT_LEGADO = re.compile(r"^from\s+(backend|src)\.", re.MULTILINE)

# Padrão: nomes de modelo hardcoded em chamadas (não em comentários nem strings de tabela)
PATRON_MODELO_CHAMADA = re.compile(
    r"""(?<![#'"])\bcall_model\s*\([^)]*"claude-(?:sonnet|haiku|opus)-[\d.-]+"""
)

erros: list[str] = []

for py in CORE_DIR.glob("*.py"):
    if py.name == "__init__.py":
        continue
    texto = py.read_text(encoding="utf-8")

    if PATRON_IMPORT_LEGADO.search(texto):
        erros.append(f"{py.name}: import legado 'from backend.' ou 'from src.' encontrado")

    if py.name != "model_adapter.py" and PATRON_CLIENT_DIRETO.search(texto):
        erros.append(f"{py.name}: anthropic.Anthropic() instanciado fora de model_adapter.py")

    if py.name not in PERMITIDO_MODELO_HARDCODE and PATRON_MODELO_CHAMADA.search(texto):
        erros.append(f"{py.name}: nome de modelo hardcoded em chamada — use env var via config.py")

if erros:
    print("[lint_core_strict] FALHOU:")
    for e in erros:
        print(f"  {e}")
    sys.exit(1)

print(f"[lint_core_strict] OK — {len(list(CORE_DIR.glob('*.py')))} arquivos verificados")
