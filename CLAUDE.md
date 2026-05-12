# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> Projeto e código em **português**. README.md cobre a arquitetura completa em detalhe — este arquivo destaca apenas o que não é óbvio ao olhar arquivos isolados.

## Comandos essenciais

### Backend (FastAPI :8082)
```bash
# Setup
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt

# Banco — Postgres dev (docker) ou SQLite (default)
docker compose up -d              # Postgres :5433 + Redis :6379
alembic upgrade head              # aplica migrations
alembic revision --autogenerate -m "msg"

# Executar
uvicorn api.main:app --host 127.0.0.1 --port 8082 --reload
```

### Frontend (Vite + React 19 :5173)
> O frontend está em **`frontend/frontend/`** (duplo aninhamento) — `frontend/` na raiz é só wrapper.
```bash
cd frontend/frontend
npm install && npm run dev
npm run build && npm run lint
```

### Testes
```bash
pytest tests/ -v
pytest tests/test_detectores_forenses.py -v          # arquivo único
pytest tests/test_api_e2e.py::nome_do_teste -v       # teste único
pytest -k "rate_limit"                                # por keyword
```
`tests/conftest.py` exporta fixtures `nfa_venda`, `parte_produtor`, `produto_simples` baseadas em `nfa_extractor.domain.extractor` — reutilize antes de inventar novas.

## Arquitetura — pontos que exigem leitura cruzada

### 1. Pipeline NFA-e é sequencial e tolerante a falha de LLM
`api/services/auditoria_nfae.py` orquestra: **RE-1 → XGBoost → F1-F6 → A-07 → A-08**. As etapas determinísticas (RE-1, XGBoost, F1-F6, A-07) **sempre rodam**; A-08 (única que depende de LLM) faz `try/except` e retorna `AgentResult(status="ERRO")` se a Anthropic API falhar. **Nunca quebre essa garantia**: o frontend mostra "IA DEGRADADO" mas o laudo precisa sair.

### 2. Protocolo @Delta — anonimização obrigatória antes de LLM
`horizon_blue_one/core/privacy.py` substitui CPF/CNPJ/nomes/razões sociais por tokens `@DELTA-001`, `@PESSOA-001`, `@EMPRESA-001` **antes** de qualquer chamada Claude/Gemini, com mapa reverso aplicado na resposta. Qualquer novo agente que envie dados a LLM deve passar por esse pipeline — não logue dados pessoais nem envie payload bruto.

### 3. Origem dos imports após consolidação dos módulos
O projeto consolidou 3 bases (NFA Extractor + Horizon-Blue + worktree). Imports migrados:
- `backend.*` → `horizon_blue_one.*`
- `src.*` → `nfa_extractor.*`
- `src/application/reports/*` → `pdf_engine/*`

Se você ver `from backend.` ou `from src.` em código novo, está errado.

### 4. Catálogo de agentes vs pipeline ativo
`horizon_blue_one/agents/` contém **28 agentes (a00–a27)** mas o pipeline em produção usa **apenas A-07 (`a07_auditoria_assurance.py`) e A-08 (`a08_auditor_nfa.py`)**. Os demais (a00-a06, a09-a27) são protótipos/reservas — não conecte ao pipeline sem alinhamento.

Todos herdam de `base_agent.py::AgentResult` (Pydantic v2, com `audit_hash` SHA-256 obrigatório para rastreabilidade).

### 5. Detectores forenses são determinísticos
`detectores_forenses.py` implementa as 5 tipologias do A-07 **sem LLM**: `CARROSSEL_FISCAL`, `SMURFING_RURAL`, `FORNECEDOR_FANTASMA`, `DEVOLUCAO_POSTERIOR`, `ANOMALIA_TEMPORAL`. Não substitua por chamadas de IA — o A-07 precisa ser auditável e reprodutível.

### 6. Modelos LLM por env var (não hardcode)
`horizon_blue_one/core/model_adapter.py` lê `SQUAD_MODEL`, `AUDITORIA_MODEL`, `AUDITORIA_MODEL_SIMPLES` do ambiente. Tem `tenacity` retry (3x, backoff 1–8s) e prompt caching. **Nunca** hardcode `claude-sonnet-4-6` ou similares no código — sempre via env.

### 7. Banco de dados — dev vs prod
- **Dev default**: SQLite em `orgatec_sovereign.db` (raiz). Auto-criado via `Base.metadata.create_all` no lifespan.
- **Prod/docker**: Postgres 16 em `:5433`. Schema controlado por `alembic/versions/` (já há 3 migrations: initial, ledger_entries, claude_stats).
- O `DATABASE_URL` controla qual backend é usado; SQLAlchemy é cross-DB.

### 8. Auth — duas gerações de hash convivem
`api/auth/security` usa **argon2id** como padrão atual mas mantém `bcrypt` para verificar hashes legados. Login é transparente: ao acertar com bcrypt, o hash é re-emitido em argon2 silenciosamente. Não remova `bcrypt` do `requirements.txt`.

### 9. Rate limit — Redis em prod, fakeredis em testes
`api/middleware/rate_limit.py` aplica 60 req/60s por IP. Em testes, troque para `fakeredis` (já em `requirements.txt`) — não dependa de Redis real em CI.

## Convenções do projeto

### Variáveis e comentários: pt-BR
Todo código novo (variáveis, funções, docstrings, comentários) em português. Nomes de schema/HTTP/SQL em inglês quando padrão da indústria (`POST /auth/login`, `created_at`).

### Branches e commits (de CONTRIBUTING.md)
- Branch: `feat/<nome>`, `fix/<nome>`, `chore/<nome>` partindo de `develop`
- Commit: `<tipo>: <descrição em pt-BR>` — tipos: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `perf`, `ci`
- PR sempre aponta para `develop`, **nunca** direto em `main`

### Checklist antes de PR
- `pytest tests/ -v` verde
- `.env.example` atualizado se adicionou env vars
- Diff sem secrets: `git diff --cached | grep -iE "key|token|password|secret"`

## Armadilhas conhecidas

- **`frontend/frontend/`**: o React app real está aninhado duas vezes. `cd frontend && npm run dev` falha — use `cd frontend/frontend`.
- **`config.env` vs `.env`**: o projeto referencia ambos em pontos diferentes; o `.env` é o canônico, `config.env` é legado/exemplo.
- **`SQUAD_MODEL` e família precisam de prefixo de provider**: o formato é `anthropic:claude-sonnet-4-6`, não só `claude-sonnet-4-6`. O `model_adapter` faz o roteamento pelo prefixo.
- **Worktrees em `.claude/worktrees/`**: ignore — são checkouts isolados para experimentos paralelos, não código ativo.
