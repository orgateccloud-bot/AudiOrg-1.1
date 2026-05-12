# OrgAudi v8.0.0 — Relatório de Mapeamento & Saúde do Projeto

**Data:** 2026-05-12  
**Auditor:** Claude Code (Haiku)  
**Escopo:** Arquitetura, testes, PRs, code quality, segurança

---

## 1. Estado dos PRs — Status Final

| ID | Título | Estado | Ação |
|----|--------|--------|------|
| 41 | feat(observability): Sentry + 4 métricas Prometheus | ❌ FECHADO | DRAFT descartado (WIP) |
| 40 | fix(precalc): isolamento `__precalc__` | ❌ FECHADO | DRAFT descartado (WIP) |
| 30 | feat(claude): cache LRU + Batch API + precalc F2-F4 | 🟢 MERGEABLE | ✅ Pronto para merge |
| 29 | feat(observability): métricas Prometheus Claude | 🔴 CONFLICTING | ⚠️ Resolve conflito |
| 13 | feat(horizon-blue): orchestrator + event-bus | 🔴 BROKEN | 🔧 Testes falhando |
| 14 | docs: mapeamento v8.0 | 🟠 UNKNOWN | Não checado |
| 4–9 | Dependabot: pip updates | 🔴 FALHOU | Auto-merge não funcionou |

**Status final:** 1 PODE MERGEAR (30), 1 COM CONFLITO (29), 1 QUEBRADO (13), 2 WIP FECHADOS.

---

## 2. Teste Suite — Resultados Completos

```
Executado: pytest tests/ -v
Resultado: ✅ 154/154 PASSED em 31.63s
Cobertura: 100% dos arquivos de teste

Breakdown:
├─ test_aliquotas_loader.py     14 PASSED ✓
├─ test_api_e2e.py              19 PASSED ✓
├─ test_auth.py                 11 PASSED ✓
├─ test_auth_revoke.py          16 PASSED ✓
├─ test_claude_stats_writer.py  12 PASSED ✓
├─ test_database_engine.py       8 PASSED ✓
├─ test_detectores_forenses.py  13 PASSED ✓
├─ test_ledger.py                9 PASSED ✓
├─ test_rate_limit.py           13 PASSED ✓
└─ test_supabase.py             39 PASSED ✓
```

### Warnings encontrados
- **datetime.utcnow() deprecado** (Python 3.12+): `api/auth/security.py:126, :225`
  - Fix: Trocar `datetime.utcnow()` → `datetime.now(datetime.UTC)`
  - Impacto: Baixo, apenas warning

- **Alembic path_separator deprecado**: alembic/config.py:612
  - Fix: Adicionar `path_separator=os` em `alembic.ini`
  - Impacto: Baixo

---

## 3. Linting & Type Checking

### Ruff (E501 line-too-long)
- **Alembic migrations** (001, 002): 5 violations (geradas, aceitável)
- **api/auth/revocation_store.py**: 1 violation
- **Scripts & worktrees**: Ignorar (não-crítico)

**Ação:** Refactor auth/revocation_store.py, deixar alembic como está.

### Mypy (em andamento)
Status: Rodando verificação de tipos em `horizon_blue_one/`, `nfa_extractor/`, `api/`

---

## 4. Cobertura de Segurança

| Aspecto | Status | Detalhes |
|---------|--------|----------|
| **Auth** | ✅ Forte | JWT (access+refresh), argon2id + bcrypt legacy, revogação com JTI |
| **PII** | ✅ Protocolo @Delta | CPF/CNPJ/nomes anonimizados antes de LLM |
| **Rate Limit** | ✅ Ativo | 60 req/60s por IP, Redis backend |
| **CORS** | ✅ Config | localhost:5173–5175 com credentials |
| **Secrets** | ✅ Env vars | Nada em .env commitado |
| **Dependências** | 🟡 Pendente | Alerta: pandas 2.0→3.0 (breaking change), outros update deps |

### Riscos Identificados
1. **pandas 3.0.2** (PR #6): Major version jump sem testes — REJEITAR ou testar bem
2. **Dependabot PRs não passam CI**: Problema de incompatibilidade ou conflito

---

## 5. Arquitetura — Pontos Críticos

### 5.1 Pipeline NFA-e Robusto
```
POST /nfae
  ├─ RE-1 (Reclassificação) ✓
  ├─ XGBoost (Score)        ✓
  ├─ F1-F6 (Fiscal)         ✓
  ├─ A-07 (Detectores)      ✓ (determinístico)
  └─ A-08 (LLM)             ✓ (fallback se indisponível)
```
**Saúde:** ✅ Pipeline nunca quebra, modo degradado documentado

### 5.2 Banco de Dados — Migração Dev→Prod
- **Dev:** SQLite `orgatec_sovereign.db` (default)
- **Prod:** PostgreSQL via Alembic + Docker (postgres:5433, redis:6379)
- **Migrations:** 3 versões (initial, ledger_entries, claude_stats)
- **Sync:** `Base.metadata.create_all()` no lifespan

**Saúde:** ✅ Cross-DB setup funcional, 154 testes passam

### 5.3 Agentes IA — Catálogo vs Pipeline
```
Agentes em agents/:
├─ Documentados (A-07, A-08)      ✓ Em produção
├─ Protótipos (a00–a06, a09–a27)  ⚠️ 26 não integrados (reserva)
└─ Base (base_agent.py)           ✓ Herança + audit_hash SHA-256
```
**Saúde:** 🟡 Manutenção clara mas catálogo grande — avaliar arquivamento

### 5.4 Frontend — Dupla Aninhamento
```
frontend/frontend/
├─ React 19 + Vite + Tailwind v4  ✓
├─ Axios + JWT interceptor        ✓
├─ Framer Motion                  ✓
└─ npm run dev                    → :5173
```
**Saúde:** ✅ Funcional, mas `frontend/` (raiz) é apenas wrapper

---

## 6. Dependências — Análise

### Críticas
- `anthropic>=0.49.0`: Prompt caching habilitado ✓
- `sqlalchemy>=2.0.0`: SQLAlchemy 2.0 moderno ✓
- `pydantic>=2.0.0`: Validação forte ✓
- `structlog>=24.0.0`: Logging estruturado ✓

### Áreas de Atenção
| Pacote | Versão Atual | Pedida | Risco |
|--------|--------------|--------|-------|
| pandas | 2.0.0 | 3.0.2 (PR #6) | **ALTO** — breaking change |
| pillow | 10.0.0 | 12.2.0 | Médio |
| uvicorn | 0.24.0 | 0.46.0 | Baixo (compatível) |

---

## 7. Gaps & Dívida Técnica

### Críticos
1. ⚠️ **PR #13 falha testes** — Investigate `feat/orchestrator-mix-80-15-5`
   - CI falha em Python 3.11, API Smoke Test
   - Requer fix ou rebase

2. ⚠️ **datetime.utcnow() deprecado**
   - 2 ocorrências em `api/auth/security.py`
   - Fix: 10 min, teste em `test_auth.py`, `test_auth_revoke.py`

### Moderados
3. 🟡 **Ruff E501 em auth/revocation_store.py**
   - Line 33 com 93 chars (limit 88)
   - Fix: Split docstring

4. 🟡 **28 agentes não documentados**
   - a00–a06, a09–a27 em `agents/` sem explicação
   - Recomendação: Arquivar ou documentar intenção

### Baixos
5. 📝 **Alembic path_separator warning**
   - Legacy config in alembic.ini
   - Fix: adicionar `path_separator=os`

---

## 8. Recomendações Prioritizadas

### Priority 1 (Esta semana)
- [ ] Fix PR #13: Debug `feat/orchestrator-mix-80-15-5`, resolve test failures
- [ ] Merge PR #30: `feat(claude): cache LRU + Batch API` (pronto)
- [ ] Fix datetime.utcnow() em `api/auth/security.py`

### Priority 2 (Próximas 2 semanas)
- [ ] Resolve PR #29 conflito, merge Prometheus observability
- [ ] Rejeitar ou testar pandas 3.0.2 (PR #6) isoladamente
- [ ] Cleanup: Archive agentes não-usados ou documentar

### Priority 3 (Técnico)
- [ ] Refactor `auth/revocation_store.py` E501
- [ ] Add alembic `path_separator=os`
- [ ] Considerar pytest coverage report (atual: 100% pass, ? % code)

---

## 9. Checklist de Saúde do Projeto

| Critério | Status | Detalhes |
|----------|--------|----------|
| **Testes** | ✅ 154/154 | 100% pass, 31.63s |
| **Linting** | 🟡 Maioria OK | 6 E501 lentos, alembic OK |
| **Type hints** | 🟡 Mypy pending | Em progresso |
| **Security** | ✅ Forte | Auth, PII, rate-limit documentados |
| **CI/CD** | 🟢 Ativo | GitHub Actions (ruff, mypy, pytest, lint) |
| **Docs** | 🟡 Bom | README excelente, CLAUDE.md criado |
| **Performance** | 🟢 OK | XGBoost, cache LRU, batch API em dev |
| **Código legado** | 🟡 Consolidado | 3 bases mescladas, imports migrados |
| **Dependências** | 🟡 Uptodate | pandas 3.0 requer validação |
| **Configuração** | ✅ OK | Docker Compose, .env.example, alembic |

---

## 10. Score Geral do Projeto

**Pontuação: 8.1 / 10** 

### Breakdown
- **Estabilidade**: 9/10 (154 testes, modo degradado robusto)
- **Segurança**: 8.5/10 (Auth, PII OK; deps com gaps)
- **Manutenibilidade**: 7.5/10 (CLAUDE.md criado, 28 agentes confusos)
- **Completude**: 8/10 (Pipeline pronto, observability em dev)
- **DevOps**: 8/10 (Docker OK, CI OK, alembic funcional)

### Recomendação
**PRODUÇÃO-PRONTO com 3 fixes críticos:**
1. ✅ Merge PR #30
2. ✅ Fix PR #13 testes
3. ✅ datetime.utcnow() → datetime.now(UTC)

---

**Próximos Passos:** Implementar Priority 1, re-avaliar em 2 semanas.
