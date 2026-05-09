"""
Migrador automático: substitui call_model(ModelType.X, ...) por
call_otimizado(...) em todos os agentes que ainda não foram migrados.

Padrão da migração:
    ANTES:
        from horizon_blue_one.core.model_adapter import call_model, ModelType
        ...
        resp = await call_model(ModelType.SONNET, prompt, SYSTEM, max_tokens=2048)

    DEPOIS:
        from horizon_blue_one.core.model_adapter import call_model, ModelType
        from horizon_blue_one.agents.a_token import call_otimizado
        from horizon_blue_one.core.token_router import TipoTarefa
        ...
        resp, _decision = await call_otimizado(prompt, SYSTEM, max_tokens=2048,
                                                agent_id=self.agent_id)

A `agent_id` faz lookup automático no _AGENTE_TAREFA do token_router,
respeitando o mix 80/15/5.

Uso:
    python scripts/migrar_call_otimizado.py            # dry-run
    python scripts/migrar_call_otimizado.py --apply    # grava arquivos
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = ROOT / "horizon_blue_one" / "agents"

# Já migrados manualmente
JA_MIGRADOS = {"a23_analista_anomalias.py", "a27_epsilon_forensic.py"}

IMPORT_BLOCK_NEW = (
    "from horizon_blue_one.agents.a_token import call_otimizado\n"
    "from horizon_blue_one.core.token_router import TipoTarefa\n"
)

# Regex de chamada: captura (ModelType.X, prompt, [system,] [max_tokens=N])
# Suporta:
#   await call_model(ModelType.SONNET, prompt, SYSTEM, max_tokens=1024)
#   await call_model(ModelType.HAIKU, prompt, SYSTEM)
#   await call_model(ModelType.CLAUDE, prompt, max_tokens=4096)
#   await call_model(ModelType.HAIKU, prompt)
RE_CALL = re.compile(
    r"await\s+call_model\(\s*ModelType\.\w+\s*,\s*([^)]+)\)",
    re.MULTILINE,
)


def migrar_arquivo(path: Path, dry: bool = True) -> dict:
    """Patches one file. Returns dict com diagnóstico."""
    txt = path.read_text(encoding="utf-8")
    original = txt
    info = {"file": path.name, "calls_antes": 0, "calls_depois": 0, "imports_add": False}

    info["calls_antes"] = len(RE_CALL.findall(txt))

    if info["calls_antes"] == 0:
        return info

    # 1) Adiciona imports se ainda não tem call_otimizado importado
    if "call_otimizado" not in txt:
        # Insere logo após o import de model_adapter
        txt2 = re.sub(
            r"(from\s+horizon_blue_one\.core\.model_adapter\s+import[^\n]+\n)",
            r"\1" + IMPORT_BLOCK_NEW,
            txt,
            count=1,
        )
        if txt2 != txt:
            txt = txt2
            info["imports_add"] = True

    # 2) Substitui cada chamada
    def _replace(m: re.Match) -> str:
        inner = m.group(1).strip().rstrip(",").strip()
        # adiciona agent_id=self.agent_id se ainda não tiver
        if "agent_id" in inner:
            args = inner
        else:
            args = inner + ", agent_id=self.agent_id"
        return f"(await call_otimizado({args}))[0]"

    txt = RE_CALL.sub(_replace, txt)
    info["calls_depois"] = len(re.findall(r"await\s+call_otimizado\(", txt))

    if not dry and txt != original:
        path.write_text(txt, encoding="utf-8")
    return info


def main(apply: bool = False) -> int:
    print(f"\n{'='*72}")
    print(f"  MIGRAÇÃO call_model -> call_otimizado  ({'APPLY' if apply else 'DRY-RUN'})")
    print(f"{'='*72}\n")

    arquivos = [
        f for f in sorted(AGENTS_DIR.glob("a*.py"))
        if f.name not in JA_MIGRADOS and not f.name.startswith("a_") and f.name != "__init__.py"
    ]

    total_chamadas = 0
    arquivos_alterados = 0
    print(f"  {'arquivo':<35} {'chamadas':>8} {'migradas':>8} {'imports':>9}")
    print("  " + "-"*65)
    for f in arquivos:
        r = migrar_arquivo(f, dry=not apply)
        if r["calls_antes"] > 0:
            arquivos_alterados += 1
            total_chamadas += r["calls_antes"]
            print(
                f"  {r['file']:<35} {r['calls_antes']:>8} {r['calls_depois']:>8}  "
                f"{'add' if r['imports_add'] else 'ok':>8}"
            )
    print("  " + "-"*65)
    print(f"  {'TOTAL':<35} {total_chamadas:>8} arquivos: {arquivos_alterados}")

    if not apply:
        print(f"\n  >> Dry-run apenas. Rode com --apply para gravar.\n")
    else:
        print(f"\n  >> {arquivos_alterados} arquivos gravados.\n")
    return 0


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    sys.exit(main(apply=apply))
