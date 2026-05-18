#!/usr/bin/env bash
# cleanup_runtime_outputs.sh
# ---------------------------------------------------------------------------
# Remove arquivos de runtime que vazaram para o git em commits anteriores.
# Esses diretorios ja estao no .gitignore - este script apenas remove o que
# ficou versionado historicamente.
#
# Uso:
#   bash scripts/cleanup_runtime_outputs.sh           # dry-run
#   bash scripts/cleanup_runtime_outputs.sh --apply   # executa de fato
#
# Apos --apply, faca commit e push:
#   git add -A
#   git commit -m "chore(cleanup): remove runtime outputs from version control"
#   git push origin main
# ---------------------------------------------------------------------------

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$REPO_ROOT"

APPLY=0
if [[ "${1:-}" == "--apply" ]]; then
  APPLY=1
fi

TARGETS=(
  "out/simulacao_*"
  "reports_nfa/EMAIL_*.txt"
  "reports_nfa/RELATORIO_TOKENS_*.md"
  "reports_nfa/llm_alto_risco_*.json"
  "reports_nfa/lote_completo_*.json"
  "reports_nfa/laudos_pdf"
)

echo "===> Cleanup runtime outputs"
echo "Mode: $([ $APPLY -eq 1 ] && echo APPLY || echo DRY-RUN)"
echo

TOTAL=0
for pattern in "${TARGETS[@]}"; do
  matches=$(git ls-files $pattern 2>/dev/null || true)
  if [[ -z "$matches" ]]; then
    echo "  [skip] No tracked files matching: $pattern"
    continue
  fi
  count=$(echo "$matches" | wc -l | tr -d ' ')
  TOTAL=$((TOTAL + count))
  echo "  [$count files] $pattern"
  if [[ $APPLY -eq 1 ]]; then
    echo "$matches" | xargs -r git rm -rf --quiet
  fi
done

echo
echo "Total tracked files matched: $TOTAL"
if [[ $APPLY -eq 1 ]]; then
  echo
  echo "===> Done. Now run:"
  echo "  git status"
  echo "  git commit -m 'chore(cleanup): remove runtime outputs from version control'"
  echo "  git push origin main"
else
  echo
  echo "Dry-run only. Re-run with --apply to delete."
fi
