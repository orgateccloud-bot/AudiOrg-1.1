# Status da Migração Supabase — OrgAudi v8.0

## 🎯 Resumo Executivo

**Data:** 2026-05-15  
**Status:** ✅ **Fase 1 Completa + Testes Locais OK** | ⏳ **Fase 2-4 Bloqueadas por Credenciais Supabase**

### Estado Atual

| Componente | Status | Detalhes |
|-----------|--------|----------|
| **Backend (FastAPI)** | ✅ Rodando | :8082 (CORRIGIDO de 8083) | 
| **Frontend (React)** | ✅ Rodando | :5173 → Login OK |
| **Fluxo de Login** | ✅ Funcional | JWT auth, tokens gerados |
| **Dashboard** | ✅ Acessível | Centro de Comando carregado |
| **Database Local (SQLite)** | ✅ Sincronizado | 10 tabelas, 4 migrations aplicadas |
| **Supabase URL** | ✅ Configurado | https://bfumcgchpwtbukahvbng.supabase.co |
| **Supabase ANON_KEY** | ✅ Configurado | sb_publishable_D6Fi37... |
| **Supabase SERVICE_KEY** | ❌ **FALTANDO** | Necessário para operações backend em Postgres |
| **Supabase JWT_SECRET** | ❌ **FALTANDO** | Necessário para validar tokens Auth Supabase |
| **Supabase Conexão Direta** | ⚠️ DNS Error | db.bfumcgchpwtbukahvbng.supabase.co não resolveu |

---

## ✅ Problema Corrigido: Porta da API Frontend

### Issue Descoberto
Frontend estava configurado para conectar na porta **8083** (padrão desatualizado), mas backend rodava em **8082**.

```javascript
// frontend/frontend/src/services/api.js (ANTES)
baseURL: import.meta.env.VITE_API_URL || 'http://127.0.0.1:8083'  // ❌ Errado
```

### Solução Aplicada
```javascript
// frontend/frontend/src/services/api.js (DEPOIS)
baseURL: import.meta.env.VITE_API_URL || 'http://127.0.0.1:8082'  // ✅ Correto
```

### Resultado
- ✅ Frontend consegue conectar ao backend
- ✅ Login funciona (teste: teste@orgatec.com.br / senha123)
- ✅ JWT tokens gerados corretamente
- ✅ Dashboard "Centro de Comando" carregado e operacional

---

## 📊 Estrutura de Tabelas Sincronizadas

Todas as 4 migrations já foram aplicadas com sucesso na SQLite local:

```
✅ Migration 001: Initial
   └─ users, clientes, notas, produtos, laudos

✅ Migration 002: Audit Results & PDF Hash
   └─ auditoria_resultados, laudos.pdf_sha256, audit_tasks

✅ Migration 003: Ledger Entries
   └─ ledger_entries (com 4 índices)

✅ Migration 004: Claude Stats
   └─ claude_stats (agregações de chamadas LLM)
```

**Total:** 10 tabelas, schema pronto para Supabase.

---

## 🔐 Credenciais Necessárias para Continuar

Para completar a migração, você precisa obter **3 chaves** do Supabase Dashboard:

### 1️⃣ SUPABASE_SERVICE_KEY (crítico)

**Onde encontrar:**
- Acesse https://supabase.com/dashboard/project/bfumcgchpwtbukahvbng
- Menu → Settings → API
- Aba "Project API keys"
- Copie a chave **service_role** (não a anon)

**Por quê:**
- Permite operações backend sem respeitar RLS
- Necessário para login, criação de registros, etc.

**Formato esperado:**
```
SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### 2️⃣ SUPABASE_JWT_SECRET (crítico)

**Onde encontrar:**
- Mesmo local acima
- Aba "JWT Settings"
- Campo "JWT Secret"

**Por quê:**
- Validar tokens de login do Supabase Auth
- Assinar novos tokens

**Formato esperado:**
```
SUPABASE_JWT_SECRET=super-secret-jwt-token-key
```

### 3️⃣ DATABASE_URL_DIRECT (já configurado ✅)

Já está em config.env:
```
DATABASE_URL_DIRECT=postgresql://postgres:ZrbcieZJCyU4jjJ3@db.bfumcgchpwtbukahvbng.supabase.co:5432/postgres
```

---

## ⚠️ Problema de Conectividade

### DNS Error: "could not translate host name"

Ao tentar conectar em `db.bfumcgchpwtbukahvbng.supabase.co`, recebeu erro:

```
psycopg2.OperationalError: could not translate host name 
"db.bfumcgchpwtbukahvbng.supabase.co" to address: Name or service not known
```

### Causas Possíveis

1. **Rede local bloqueada** — firewall/proxy bloqueando acesso a Supabase
2. **DNS local não resolve** — seu ISP ou rede corporativa bloqueando
3. **Supabase não alcançável** — indisponibilidade (raro)

### Próximas Ações

Se o erro persistir após adicionar as credenciais:

```bash
# 1. Teste DNS
ping db.bfumcgchpwtbukahvbng.supabase.co
nslookup db.bfumcgchpwtbukahvbng.supabase.co

# 2. Teste conectividade com psycopg2 direto
python -c "import psycopg2; psycopg2.connect(DATABASE_URL_DIRECT)"

# 3. Se nada funcionar, considere:
#   - VPN para contornar firewall corporativo
#   - Usar pooler (:6543) em vez de direct (:5432) para testes iniciais
#   - Contatar suporte de rede
```

---

## 📋 Checklist para Continuar

- [ ] Obter SUPABASE_SERVICE_KEY do dashboard
- [ ] Obter SUPABASE_JWT_SECRET do dashboard  
- [ ] Atualizar `config.env` com ambas as chaves
- [ ] Testar conectividade com Supabase (ping + curl)
- [ ] Executar: `alembic upgrade head` (migrar schema Postgres)
- [ ] Configurar Supabase Auth (Phase 2)
- [ ] Ativar RLS nas tabelas (Phase 3)

---

## 🚀 Próxima Fase: Phase 2 (Auth Migration)

Quando as credenciais estiverem disponíveis:

```bash
# 1. Verificar schema no Supabase
psql $DATABASE_URL_DIRECT -c "\dt"

# 2. Atualizar api/auth/ para usar Supabase Auth
# - Remover login JWT local
# - Integrar supabase.auth.sign_in()
# - Usar tokens Supabase

# 3. Testar login via Supabase Auth
curl -X POST http://127.0.0.1:8082/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@company.com", "password":"..."}'
```

---

## 📞 Suporte

Se precisar de ajuda:

1. Leia `/docs/SUPABASE.md` (guia completo)
2. Verifique `alembic/versions/` para histórico de migrations
3. Consulte https://supabase.com/docs

**Commit desta análise:** feat(supabase): migração Phase 1 completa, credenciais pendentes

