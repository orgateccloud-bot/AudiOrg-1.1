# Integração Supabase — OrgAudi

Guia completo para configurar e usar o Supabase como backend de dados e serviços do OrgAudi Sovereign v8.0.

## Visão Geral da Arquitetura

O OrgAudi usa o Supabase em duas camadas complementares:

**Camada 1 — Banco de Dados (SQLAlchemy + Alembic):** Conexão direta ao PostgreSQL do Supabase via `DATABASE_URL`. Todos os models ORM, queries e migrations continuam funcionando exatamente como antes, sem mudança no código de negócio.

**Camada 2 — SDK Supabase (supabase-py):** Acesso às APIs nativas do Supabase — Auth, Storage, Realtime e RPC — disponibilizado via `get_supabase_client()` em `api/dependencies.py`.

## Pré-requisitos

- Conta no [Supabase](https://supabase.com) (free tier funciona para dev)
- Projeto Supabase criado na região `sa-east-1` (São Paulo)
- Python 3.10+ com dependências instaladas: `pip install -r requirements.txt`

## 1. Obtendo as Chaves

Acesse **Supabase Dashboard → seu projeto → Settings → API**:

| Variável | Onde obter | Uso |
|----------|-----------|-----|
| `SUPABASE_URL` | Settings → API → Project URL | URL base de todas as chamadas |
| `SUPABASE_ANON_KEY` | Settings → API → Project API keys → anon/public | Operações de usuário (com RLS) |
| `SUPABASE_SERVICE_ROLE_KEY` | Settings → API → Project API keys → service_role | Operações admin backend (bypassa RLS) |
| `SUPABASE_JWT_SECRET` | Settings → API → JWT Settings → JWT Secret | Verificação de tokens Supabase Auth |
| `DATABASE_URL` | Settings → Database → Connection string → URI (Transaction Pooler) | SQLAlchemy runtime (porta 6543) |
| `DATABASE_URL_DIRECT` | Settings → Database → Connection string → URI (Direct) | Alembic migrations (porta 5432) |

## 2. Configuração Local (Desenvolvimento)

### 2.1 Criar `config.env`

```bash
cp .env.example config.env
# Edite config.env com os valores reais do seu projeto Supabase
```

### 2.2 Carregar variáveis

```bash
# Linux/macOS
export $(grep -v '^#' config.env | xargs)

# Windows PowerShell
Get-Content config.env | Where-Object { $_ -notmatch '^#' -and $_ -ne '' } | ForEach-Object {
    $name, $value = $_ -split '=', 2
    [System.Environment]::SetEnvironmentVariable($name, $value, 'Process')
}
```

### 2.3 Rodar as Migrations no Supabase

Sempre use `DATABASE_URL_DIRECT` (porta 5432) para migrations — o Transaction Pooler (porta 6543) não suporta DDL:

```bash
# Exportar a direct connection
export DATABASE_URL="$DATABASE_URL_DIRECT"

# Aplicar todas as migrations
alembic upgrade head

# Verificar status
alembic current
```

### 2.4 Iniciar a API

```bash
uvicorn api.main:app --reload --port 8082
```

## 3. Usando o Cliente Supabase na API

O `get_supabase_client()` retorna um singleton `supabase.Client` pronto para uso:

### Exemplo: Listar dados via SDK

```python
from api.dependencies import get_supabase_client
from supabase import Client
from fastapi import APIRouter, Depends

router = APIRouter()

@router.get("/clientes")
async def listar_clientes(supa: Client = Depends(get_supabase_client)):
    response = supa.table("clientes").select("*").execute()
    return response.data
```

### Exemplo: Supabase Auth — verificar usuário logado

```python
@router.get("/perfil")
async def perfil(
    authorization: str = Header(...),
    supa: Client = Depends(get_supabase_client)
):
    token = authorization.replace("Bearer ", "")
    user = supa.auth.get_user(token)
    return {"id": user.user.id, "email": user.user.email}
```

### Exemplo: Supabase Storage — upload de PDF

```python
@router.post("/upload/{client_id}")
async def upload_pdf(
    client_id: str,
    file: UploadFile,
    supa: Client = Depends(get_supabase_client)
):
    contents = await file.read()
    path = f"{client_id}/{file.filename}"
    supa.storage.from_("laudos-pdf").upload(path, contents)
    return {"path": path}
```

## 4. Configuração Kubernetes (Produção / Staging)

### 4.1 Criar o Secret

```bash
# Usando o script automático
chmod +x scripts/setup_supabase_secret.sh
./scripts/setup_supabase_secret.sh orgaudi        # produção
./scripts/setup_supabase_secret.sh orgaudi-staging # staging
```

Ou manualmente:

```bash
kubectl create secret generic orgaudi-supabase \
  --from-literal=SUPABASE_URL="https://<ref>.supabase.co" \
  --from-literal=SUPABASE_ANON_KEY="<anon_key>" \
  --from-literal=SUPABASE_SERVICE_ROLE_KEY="<service_role_key>" \
  --from-literal=SUPABASE_JWT_SECRET="<jwt_secret>" \
  --from-literal=DATABASE_URL="postgresql://postgres.<ref>:<pwd>@aws-1-sa-east-1.pooler.supabase.com:6543/postgres" \
  --from-literal=DATABASE_URL_DIRECT="postgresql://postgres:<pwd>@db.<ref>.supabase.co:5432/postgres" \
  --from-literal=JWT_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(64))')" \
  -n orgaudi
```

### 4.2 Rodar Migrations em Produção

```bash
# Job Kubernetes para migrations (executar antes do deploy)
kubectl run alembic-migrate \
  --image=ghcr.io/orgateccloud-bot/orgaudi-api:v8.0.0 \
  --restart=Never \
  --namespace=orgaudi \
  --env="DATABASE_URL=$(kubectl get secret orgaudi-supabase -n orgaudi -o jsonpath='{.data.DATABASE_URL_DIRECT}' | base64 -d)" \
  -- alembic upgrade head
```

### 4.3 Deploy Helm

```bash
# Produção
helm upgrade --install orgaudi k8s/helm/orgaudi-chart \
  -f k8s/helm/orgaudi-chart/values-prod.yaml \
  -n orgaudi --create-namespace

# Staging
helm upgrade --install orgaudi k8s/helm/orgaudi-chart \
  -f k8s/helm/orgaudi-chart/values-staging.yaml \
  -n orgaudi-staging --create-namespace
```

## 5. Row Level Security (RLS) — Próximos Passos

O OrgAudi atualmente conecta ao Supabase como usuário `postgres` (service role), o que bypassa o RLS. Para ativar segurança por usuário:

1. Ativar RLS nas tabelas via Supabase Dashboard → Table Editor → Enable RLS
2. Criar policies de acesso (ex: usuário só vê seus próprios laudos)
3. Migrar autenticação para Supabase Auth (substituindo JWT próprio)
4. Usar `SUPABASE_ANON_KEY` nas chamadas autenticadas (respeita RLS)

## 6. Variáveis de Ambiente — Referência Completa

| Variável | Obrigatória | Descrição |
|----------|-------------|-----------|
| `SUPABASE_URL` | Sim | URL do projeto Supabase |
| `SUPABASE_ANON_KEY` | Sim* | Chave pública (com RLS) |
| `SUPABASE_SERVICE_ROLE_KEY` | Sim* | Chave admin (bypassa RLS) |
| `SUPABASE_JWT_SECRET` | Não | Para verificar tokens Supabase Auth |
| `DATABASE_URL` | Sim (prod) | Transaction Pooler — runtime |
| `DATABASE_URL_DIRECT` | Sim (migrations) | Direct — apenas para Alembic |

*Pelo menos uma das duas chaves (anon ou service_role) é necessária para `get_supabase_client()`.

---

**Dúvidas?** Consulte a [documentação oficial do Supabase](https://supabase.com/docs) ou abra uma issue neste repositório.
