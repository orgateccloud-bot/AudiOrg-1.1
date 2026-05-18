# OrgAudi — Plataforma de Auditoria Fiscal

**Versão:** 1.1.0
**Pilha:** FastAPI · React 19 · LangGraph · Claude/Gemini · XGBoost · Supabase Postgres (SQLite em dev) · ReportLab · Sentry · Prometheus
**Responsável:** ORGATEC IA

---

## Visão Geral

OrgAudi é a plataforma unificada de auditoria de Notas Fiscais Avulsas (NFA-e) da ORGATEC. Integra extração de PDF, pipeline analítico determinístico, agentes de IA e geração de relatórios em um único sistema multi-módulo.

O projeto consolida três bases de código anteriores (NFA Extractor, Horizon-Blue e worktree `great-hypatia`) em uma estrutura limpa de quatro módulos.

---

## Arquitetura — 4 Módulos

```
OrgAudi/
├── horizon_blue_one/           # Pipeline de auditoria HORIZON-BLUE ONE
├── nfa_extractor/              # Extração de PDF e infraestrutura de dados
├── pdf_engine/                 # Geração de relatórios OrgAudi
├── nfa_reports/                # Templates e ativos de relatório
├── api/                        # FastAPI — Backend unificado
│   ├── middleware/
│   │   └── sentry.py           # Sentry SDK com filtro LGPD (@Delta)
│   └── routes/
│       └── prometheus.py       # /metrics — 4 métricas Prometheus
├── front-end/                  # React 19 + Vite + Tailwind v4
├── alembic/                    # Migrações Alembic
├── k8s/                        # Manifests Kubernetes
├── data/                       # Dados versionados (alíquotas FUNRURAL etc.)
├── docs/                       # Documentação técnica
├── scripts/                    # Scripts utilitários
├── tests/                      # Suíte de testes
└── orgatec_sovereign.db        # SQLite (fallback dev)
```

---

## Módulo 1 — horizon_blue_one

Pipeline sequencial de auditoria fiscal: **RE-1 → XGBoost → F1-F6 → A-07 → A-08**

```
horizon_blue_one/
├── agents/
│   ├── base_agent.py               # AgentResult (Pydantic v2, SHA-256 audit_hash)
│   ├── a07_auditoria_assurance.py
│   ├── a08_auditor_nfa.py
│   └── detectores_forenses.py
├── core/
│   ├── config.py
│   ├── model_adapter.py            # Claude Sonnet / Haiku / Opus + retry com tenacity
│   ├── precalc.py                  # Isolamento __precalc__ via ContextVar + deepcopy (thread-safe)
│   └── privacy.py                  # Protocolo @Delta — anonimização CPF/CNPJ/nomes
├── ml/
│   └── xgboost_scorer.py           # 8 features × pesos SEFAZ-GO → score 0–100
└── orgaudi/
    ├── regra_especial_1.py         # RE-1: VENDA → COMPRA rural (aprovada CRC-GO)
    └── resumo_fiscal.py            # F1-F6: FUNRURAL 2026
```

### Pipeline de Auditoria

| Etapa | Componente | Descrição |
|---|---|---|
| RE-1 | `regra_especial_1.py` | Reclassifica VENDA em COMPRA rural para destinatário PF |
| Score | `xgboost_scorer.py` | Score de risco 0–100 com 8 features calibradas |
| Fiscal | `resumo_fiscal.py` | Apuração F1–F6: FUNRURAL, IRPF, resultado rural |
| A-07 | `a07_auditoria_assurance.py` | Detectores forenses — 5 tipologias determinísticas |
| A-08 | `a08_auditor_nfa.py` | Análise qualitativa via LLM (com fallback determinístico) |

### Detectores Forenses (A-07)

Todos são determinísticos — sem dependência de LLM:

- **CARROSSEL_FISCAL**: mesmo CNPJ aparece como emitente E destinatário.
- **SMURFING_RURAL**: múltiplas notas abaixo do limiar de tributação no mesmo dia.
- **FORNECEDOR_FANTASMA**: fornecedor com volume alto, sem histórico recorrente.
- **DEVOLUCAO_POSTERIOR**: nota de devolução emitida muito depois da original.
- **ANOMALIA_TEMPORAL**: concentração de emissões em finais de semana ou feriados.

---

## Módulo 2 — nfa_extractor

```
nfa_extractor/
├── domain/
│   ├── extractor.py            # Campos: cabeçalho, destinatario_cpf, regra_aplicada
│   ├── schemas.py
│   ├── constants.py
│   ├── nfa_ai_schemas.py
│   └── nfa_parser_ai.py
├── infrastructure/
│   ├── database_v2.py
│   ├── logging_config.py
│   ├── ai_client.py
│   ├── claude_validator.py
│   ├── audit_task_repo.py
│   └── supabase/
├── application/
│   ├── agents_engine.py
│   ├── analytics_engine.py
│   ├── audit_service.py
│   ├── extraction_orchestrator.py
│   └── sovereign_engine.py
└── utils/
    └── validators.py
```

---

## Módulo 3 — pdf_engine

Geração de relatórios fiscais em PDF via ReportLab.

---

## Módulo 4 — API

Backend FastAPI unificado com JWT, rate limiting, observabilidade e pipeline NFA-e.

### Endpoints Principais

| Método | Rota | Descrição |
|---|---|---|
| POST | `/nfae` | Executa pipeline completo de auditoria NFA-e |
| GET | `/resultado/{id}` | Recupera resultado de auditoria |
| GET | `/relatorio/{id}/pdf` | Download do relatório em PDF |
| POST | `/upload/{client_id}` | Upload de PDFs para processamento em lote |
| GET | `/status/{task_id}` | Status de processamento assíncrono |
| POST | `/auth/login` | Autenticação JWT |
| GET | `/ping` | Health check |
| GET | `/stats` | Estatísticas acumuladas do sistema |
| GET | `/metrics` | Métricas Prometheus (nfa_auditorias_total, nfa_duracao_segundos, nfa_erros_total, nfa_score_risco) |

---

## Observabilidade — Sentry + Prometheus

### Sentry (api/middleware/sentry.py)

Captura exceções não tratadas com filtro LGPD integrado:

- **Filtro @Delta automático**: CPF, CNPJ e campos PII são removidos dos eventos antes do envio (LGPD Art. 37).
- **Variável de ambiente**: `SENTRY_DSN` — se ausente, Sentry não é inicializado (fail-safe).
- **Fingerprinting**: agrupa erros por tipo de exceção para reduzir ruído.

### Prometheus (api/routes/prometheus.py)

Endpoint `GET /metrics` expõe 4 métricas:

| Métrica | Tipo | Descrição |
|---|---|---|
| `nfa_auditorias_total` | Counter | Total de auditorias executadas por status |
| `nfa_duracao_segundos` | Histogram | Duração do pipeline de auditoria |
| `nfa_erros_total` | Counter | Total de erros por módulo |
| `nfa_score_risco` | Histogram | Distribuição dos scores XGBoost (0–100) |

---

## Como Executar

### Backend

```bash
pip install fastapi uvicorn sqlalchemy pydantic anthropic xgboost numpy \
            pdfplumber reportlab structlog tenacity sentry-sdk prometheus-client
uvicorn api.main:app --host 127.0.0.1 --port 8082 --reload
```

### Front-end

```bash
cd front-end && npm install && npm run dev
```

---

## Variáveis de Ambiente

```env
ANTHROPIC_API_KEY=sk-ant-...
SQUAD_MODEL=anthropic:claude-sonnet-4-6
AUDITORIA_MODEL=anthropic:claude-sonnet-4-6
AUDITORIA_MODEL_SIMPLES=anthropic:claude-haiku-4-5-20251001

# Observabilidade
SENTRY_DSN=https://<chave>@o0.ingest.sentry.io/<projeto>   # opcional
PROMETHEUS_ENABLED=true

# Produção (Supabase Postgres Transaction Pooler — porta 6543):
DATABASE_URL=postgresql://postgres.<ref>:<pwd>@aws-1-sa-east-1.pooler.supabase.com:6543/postgres
# Dev local (omita DATABASE_URL para usar SQLite fallback)
# DATABASE_URL=sqlite:///./orgatec_sovereign.db
```

Veja `.env.exemplo` na raiz para a lista completa.

---

## Fluxo de Dados — Pipeline NFA-e

```
POST /nfae
├── RE-1    → Reclassifica VENDA para COMPRA rural (PF)
├── XGBoost → score 0–100 + nível BAIXO/MÉDIO/ALTO/CRÍTICO
├── F1-F6   → FUNRURAL + IRPF + resultado rural
├── A-07    → 5 detectores forenses determinísticos
└── A-08    → Análise qualitativa LLM + Protocolo @Delta
```

---

## Privacidade — Protocolo @Delta

Antes de enviar dados ao LLM, `privacy.py` substitui CPF/CNPJ/nomes por tokens `@DELTA-001`, `@PESSOA-001`, `@EMPRESA-001`. O mapa de reversão é aplicado na resposta.

O mesmo filtro é aplicado no middleware Sentry — nenhum dado pessoal trafega para serviços externos.

---

## Modo Degradado

Quando a API Claude está indisponível: A-07 e A-08 retornam `AgentResult(status="ERRO")`, o pipeline continua com score XGBoost e fiscal F1-F6 íntegros. O front-end exibe o emblema **"IA DEGRADADO"**.

---

## Segurança

- JWT obrigatório em todas as rotas (exceto `/ping`, `/`, `/auth/login`).
- Rate limiting: 60 requisições/min por IP.
- Protocolo @Delta: dados pessoais **nunca** trafegam para LLMs externos.
- `audit_hash` SHA-256 em cada `AgentResult`.
- Isolamento de estado de pré-cálculo via `ContextVar` + `deepcopy` (`precalc.py`) — previne vazamento de dados entre requisições concorrentes.

Detalhes em **SECURITY.md**.

---

## Testes

```bash
pytest tests/ -v
```

Cobertura incluída:

- `tests/test_precalc_isolamento.py` — 7 testes de isolamento concorrente (PrecalcLock, ContextVar)
- Testes de pipeline (A-07, XGBoost, fiscal F1-F6)
- Testes de API (endpoints FastAPI via TestClient)

---

## Governança do Projeto

- **Licença:** ver LICENSE.
- **Contribuição:** ver CONTRIBUTING.md.
- **Catálogo de agentes:** ver AGENT_CATALOG.md.
- **Integração / onboarding:** ver INTEGRATION.md e CLAUDE.md.
- **Score de qualidade:** ver ATUALIZADO_SCORE_9.0.md.
- **Migrações de banco:** Alembic em `alembic/` (`alembic.ini` na raiz).
- **Docker:** `docker-compose.yml` (apenas Redis — Postgres migrado para Supabase cloud).
- **Pré-commit:** `.pre-commit-config.yaml` (ruff, mypy, bandit).

---

## Histórico de Versões

| Versão | Data | Destaques |
|---|---|---|
| 1.1.0 | 2026-05-18 | Sentry + Prometheus (obs.), isolamento precalc via ContextVar, testes concorrência |
| 1.0.0 | 2026-05-15 | Release inicial — pipeline NFA-e completo |
