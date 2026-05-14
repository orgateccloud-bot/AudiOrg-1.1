#!/usr/bin/env bash
# =============================================================================
# OrgAudi — Setup do Kubernetes Secret para credenciais Supabase
# =============================================================================
#
# Uso:
#   chmod +x scripts/setup_supabase_secret.sh
#   ./scripts/setup_supabase_secret.sh [NAMESPACE]
#
# Argumentos:
#   NAMESPACE  Namespace Kubernetes (default: orgaudi)
#
# O script solicita interativamente as chaves Supabase, nunca as loga,
# e aplica o Secret via kubectl dry-run + apply.
#
# Pré-requisitos:
#   - kubectl instalado e configurado com o cluster correto
#   - Chaves disponíveis em: Supabase Dashboard → Settings → API
# =============================================================================

set -euo pipefail

NAMESPACE=${1:-orgaudi}
SECRET_NAME="orgaudi-supabase"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  OrgAudi — Configuração do Secret Supabase no Kubernetes"
echo "  Namespace: ${NAMESPACE}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Obtenha as chaves em: Supabase Dashboard → Settings → API"
echo ""

# Leitura segura (sem eco no terminal)
read -rp "SUPABASE_URL (ex: https://xxxx.supabase.co): " SUPABASE_URL
read -rsp "SUPABASE_ANON_KEY: " SUPABASE_ANON_KEY; echo ""
read -rsp "SUPABASE_SERVICE_ROLE_KEY: " SUPABASE_SERVICE_ROLE_KEY; echo ""
read -rsp "SUPABASE_JWT_SECRET: " SUPABASE_JWT_SECRET; echo ""
read -rp "DATABASE_URL (Transaction Pooler porta 6543): " DATABASE_URL
read -rp "DATABASE_URL_DIRECT (porta 5432, apenas para Alembic): " DATABASE_URL_DIRECT
echo ""
echo "Gerando JWT_SECRET_KEY aleatório..."
JWT_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(64))" 2>/dev/null || openssl rand -base64 64 | tr -d '\n/')
echo ""

# Criar namespace se não existir
if ! kubectl get namespace "${NAMESPACE}" &>/dev/null; then
  echo "Criando namespace ${NAMESPACE}..."
  kubectl create namespace "${NAMESPACE}"
fi

echo "Aplicando Secret '${SECRET_NAME}' no namespace '${NAMESPACE}'..."

kubectl create secret generic "${SECRET_NAME}" \
  --from-literal=SUPABASE_URL="${SUPABASE_URL}" \
  --from-literal=SUPABASE_ANON_KEY="${SUPABASE_ANON_KEY}" \
  --from-literal=SUPABASE_SERVICE_ROLE_KEY="${SUPABASE_SERVICE_ROLE_KEY}" \
  --from-literal=SUPABASE_JWT_SECRET="${SUPABASE_JWT_SECRET}" \
  --from-literal=DATABASE_URL="${DATABASE_URL}" \
  --from-literal=DATABASE_URL_DIRECT="${DATABASE_URL_DIRECT}" \
  --from-literal=JWT_SECRET_KEY="${JWT_SECRET_KEY}" \
  --namespace="${NAMESPACE}" \
  --dry-run=client -o yaml | kubectl apply -f -

echo ""
echo "✅ Secret '${SECRET_NAME}' configurado com sucesso!"
echo ""
echo "Próximos passos:"
echo "  1. Rode as migrations no Supabase:"
echo "     DATABASE_URL_DIRECT=<direct_url> alembic upgrade head"
echo "  2. Faça o deploy do Helm chart:"
echo "     helm upgrade --install orgaudi k8s/helm/orgaudi-chart \"
echo "       -f k8s/helm/orgaudi-chart/values-prod.yaml \"
echo "       -n ${NAMESPACE}"
echo ""

# Limpar variáveis sensíveis da memória do processo
unset SUPABASE_ANON_KEY SUPABASE_SERVICE_ROLE_KEY SUPABASE_JWT_SECRET JWT_SECRET_KEY DATABASE_URL DATABASE_URL_DIRECT
