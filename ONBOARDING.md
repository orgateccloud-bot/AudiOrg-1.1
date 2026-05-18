# OrgAudi v8.0.0 — Guia de Onboarding (5 minutos)

## Setup Rápido

### 1. Clone + Ambiente
```bash
git clone https://github.com/orgateccloud-bot/AudiOrg-1.1.git
cd AudiOrg-1.1

# Virtual env
python -m venv .venv
.venv\Scripts\activate  # Windows

# Instalar
pip install -r requirements.txt
```

### 2. Banco de Dados (escolha uma)

**Opção A: SQLite (dev padrão — nenhum setup necessário)**
```bash
# Pronto! orgatec_sovereign.db é auto-criado
```

**Opção B: Postgres (docker)**
```bash
docker compose up -d
alembic upgrade head
```

### 3. Variáveis de Ambiente

```bash
# Copie e edite
cp .env.example .env

# Mínimo para dev:
ANTHROPIC_API_KEY=sk-ant-...
JWT_SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
```

### 4. Rodar Testes (confirmação de setup)
```bash
pytest tests/ -v  # 154 tests, ~32s
```

### 5. Rodar App

**Backend** (FastAPI)
```bash
uvicorn api.main:app --host 127.0.0.1 --port 8082 --reload
# → http://127.0.0.1:8082
```

**Frontend** (React, em outro terminal)
```bash
cd frontend/frontend
npm install && npm run dev
# → http://localhost:5173
```

---

## Estrutura do Projeto (30 segundos)

```
OrgAudi/
├── horizon_blue_one/     Pipeline de auditoria (RE-1 → XGBoost → F1-F6 → A-07 → A-08)
├── nfa_extractor/        Extração PDF + DB
├── pdf_engine/           Geração de relatórios
├── api/                  FastAPI backend
├── frontend/frontend/    React UI
├── tests/                154 testes (pytest)
└── alembic/              Migrations Postgres/SQLite
```

**Atalhos úteis:**
- `horizon_blue_one/agents/`: 2 produção (a07, a08), 26 protótipos
- `api/routes/`: endpoints CRUD (auth, auditoria, clientes, agente, nfa_ai_parser)
- `nfa_extractor/domain/`: Pydantic schemas (NFA, Parte, Produto)

---

## Comandos Essenciais

```bash
# Testes
pytest tests/ -v                            # Todos
pytest tests/test_detectores_forenses.py    # Um arquivo
pytest -k "auth"                            # Por keyword

# Linting
python -m ruff check .                      # Lint
python -m mypy horizon_blue_one/            # Type check

# Database
alembic revision --autogenerate -m "desc"  # Nova migration
alembic upgrade head                        # Aplicar migrations
alembic downgrade -1                        # Reverter

# Dev server
uvicorn api.main:app --reload              # Hot reload
npm run dev                                 # React dev server
```

---

## Fluxo Comum: Auditar uma NFA

```python
# Em Python REPL ou script
from horizon_blue_one.agents.a08_auditor_nfa import auditar_nfa
from nfa_extractor.domain.extractor import extrair_notas

# 1. Extrair PDF
notas = extrair_notas("documento.pdf")

# 2. Auditar (pipeline completo)
resultado = auditar_nfa(notas, cliente_cpf="123.456.789-00")

# 3. Ver resultado
print(resultado.status)        # "OK" ou "ERRO"
print(resultado.audit_hash)    # SHA-256 para rastreability
```

Ou via API REST:
```bash
curl -X POST http://localhost:8082/nfae \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"notas": [...], "cpf": "..."}'
```

---

## Troubleshooting Rápido

| Problema | Solução |
|----------|---------|
| `ModuleNotFoundError: horizon_blue_one` | `pip install -e .` na raiz |
| Tests falhando | Rodar `pytest tests/ -v` (pré-requisitos: DB, env vars) |
| Frontend erro CORS | Backend responde em 8082, frontend em 5173 (proxy em vite.config.js) |
| `sqlite3.OperationalError: database is locked` | Feche outros processos Python; SQLite não multi-process |
| `ANTHROPIC_API_KEY not set` | Copie `.env.example` → `.env`, edite com chave real |

---

## Próximos Passos

1. **Primeiro Bug Fix**: `git checkout -b fix/meu-bug` → teste local → PR para `develop`
2. **Feature Nova**: `git checkout -b feat/meu-feature` → código → tests → PR
3. **Dúvidas**: Ver `CLAUDE.md` (arquitetura técnica), `CONTRIBUTING.md` (workflow)

---

**Bem-vindo ao OrgAudi!** 🚀
