# OrgAudi Sovereign — Plataforma de Auditoria Fiscal

**Versão:** 8.1.0
**Stack:** FastAPI · React 19 · LangGraph · Claude/Gemini · XGBoost · SQLite · ReportLab
**Responsável:** ORGATEC IA

---

## Changelog — v8.1.0

Refatoração arquitetônica completa implementada em 6 fases (P1-A, P1-B, P2-A, P2-B, P3-A, P3-B).

### P1-B — Campo cabecas e Melhorias no Extrator NFA

- Adicionado campo `cabecas` (int) ao dataclass `NFA` em `extractor.py`
- Adicionado campo `destinatario_cpf` para captura direta do CPF do destinatário
- Adicionado campo `regra_aplicada` para rastrear qual regra fiscal foi aplicada

### P1-A — ExtractionOrchestrator

- Criado `nfa_extractor/application/extraction_orchestrator.py`
- Orquestrador centralizado para extração em lote de PDFs com controle de estado
- Suporte a processamento paralelo via asyncio com rastreamento de progresso

### P2-B — Remoção de Dependência google-genai

- Removida dependência `google-genai` do `requirements.txt`
- Mantida apenas integração via `google-generativeai` (API REST direta)
- Redução do tamanho da imagem Docker em ~180MB
- Elimina conflito de versão com `anthropic>=0.40`

### P2-A — Script de Arquivamento de Agentes Legados

- Criado `scripts/archive_agents.sh` para mover agentes descontinuados para `_archive/`
- Script idempotente — não destrói dados, apenas move com timestamp

### P3-A — Guia de Unificação ai_client.py

- Criado `docs/P3A_UNIFICAR_AI_CLIENT.md` com guia técnico detalhado
- Interface única `AIClient` com `generate()` e `generate_structured()`

### P3-B — Validador Claude

- Criado `nfa_extractor/infrastructure/claude_validator.py`
- Validação estruturada de respostas Claude via Pydantic v2
- Retry automático com backoff exponencial (tenacity)

---

## Visão Geral

OrgAudi é a plataforma unificada de auditoria de Notas Fiscais Avulsas (NFA-e) da ORGATEC. Integra extração de PDF, pipeline analítico determinístico, agentes de IA e geração de relatórios em um único sistema multi-módulo.

O projeto consolida três bases de código anteriores (NFA Extractor, Horizon-Blue, worktree `great-hypatia`) em uma estrutura limpa de quatro módulos.
*OrgAudi Sovereign Shield — ORGATEC v8.1.0*
**Versão:** 8.0.0  
**Stack:** FastAPI · React 19 · LangGraph · Claude/Gemini · XGBoost · SQLite · ReportLab  
**Responsável:** ORGATEC IA

---

## Visão Geral

OrgAudi é a plataforma unificada de auditoria de Notas Fiscais Avulsas (NFA-e) da ORGATEC. Integra extração de PDF, pipeline analítico determinístico, agentes de IA e geração de relatórios em um único sistema multi-módulo.

O projeto consolida três bases de código anteriores (NFA Extractor, Horizon-Blue, worktree `great-hypatia`) em uma estrutura limpa de quatro módulos.

---

## Arquitetura — 4 Módulos

```
OrgAudi/
├── horizon_blue_one/     # Pipeline de auditoria HORIZON-BLUE ONE
├── nfa_extractor/        # Extração de PDF e infraestrutura de dados
├── pdf_engine/           # Geração de relatórios OrgAudi v2.4–v2.5
├── api/                  # FastAPI v8.0.0 — Backend unificado
├── frontend/             # React 19 + Vite + Tailwind v4
└── orgatec_sovereign.db  # SQLite — clientes e laudos
```

---

## Módulo 1 — horizon_blue_one

Pipeline sequencial de auditoria fiscal: **RE-1 → XGBoost → F1-F6 → A-07 → A-08**

```
horizon_blue_one/
├── agents/
│   ├── base_agent.py            # AgentResult (Pydantic v2, SHA-256 audit_hash)
│   ├── a07_auditoria_assurance.py  # Agente forense — 5 detectores determinísticos
│   ├── a08_auditor_nfa.py       # Agente auditor NFA-e com Protocolo @Delta
│   └── detectores_forenses.py   # CARROSSEL_FISCAL, SMURFING_RURAL, FORNECEDOR_FANTASMA,
│                                #   DEVOLUCAO_POSTERIOR, ANOMALIA_TEMPORAL
├── core/
│   ├── config.py                # Env vars e constantes do sistema
│   ├── model_adapter.py         # Claude Sonnet 4.6 / Haiku 4.5 / Opus 4.7
│   │                            #   tenacity retry (3x, 1–8s backoff), prompt caching
│   └── privacy.py               # Protocolo @Delta — anonimização CPF/CNPJ/nomes

---

## Arquitetura — 4 Módulos

```
OrgAudi/
├── horizon_blue_one/    # Pipeline de auditoria HORIZON-BLUE ONE
├── nfa_extractor/       # Extração de PDF e infraestrutura de dados
├── pdf_engine/          # Geração de relatórios OrgAudi v2.4-v2.5
├── api/                 # FastAPI v8.0.0 — Backend unificado
├── frontend/            # React 19 + Vite + Tailwind v4
├── scripts/             # Scripts utilitários (archive_agents.sh) [NOVO v8.1.0]
├── docs/                # Documentação técnica (P3A_UNIFICAR_AI_CLIENT.md) [NOVO v8.1.0]
└── orgatec_sovereign.db # SQLite — clientes e laudos
```

---

## Módulo 1 — horizon_blue_one

Pipeline sequencial de auditoria fiscal: RE-1 → XGBoost → F1-F6 → A-07 → A-08

```
horizon_blue_one/
├── agents/
│   ├── base_agent.py                 # AgentResult (Pydantic v2, SHA-256 audit_hash)
│   ├── a07_auditoria_assurance.py    # Agente forense — 5 detectores determinísticos
│   ├── a08_auditor_nfa.py            # Agente auditor NFA-e com Protocolo @Delta
│   └── detectores_forenses.py
├── core/
│   ├── config.py
│   ├── model_adapter.py              # Claude Sonnet 4.6 / Haiku 4.5 / Opus 4.7
│   └── privacy.py                   # Protocolo @Delta — anonimização CPF/CNPJ/nomes
├── ml/
│   └── xgboost_scorer.py            # 8 features × pesos SEFAZ-GO → score 0–100
└── orgaudi/
    ├── regra_especial_1.py          # RE-1: VENDA → COMPRA rural (aprovada CRC-GO)
    └── resumo_fiscal.py             # F1-F6: FUNRURAL 2026
```

### Pipeline de Auditoria

| Etapa  | Componente                     | Descrição                                             |
|--------|--------------------------------|-------------------------------------------------------|
| RE-1   | regra_especial_1.py            | Reclassifica VENDA em COMPRA rural para destinatário PF |
| Score  | xgboost_scorer.py              | Score de risco 0–100 com 8 features calibradas        |
| Fiscal | resumo_fiscal.py               | Apuração F1–F6: FUNRURAL, IRPF, resultado rural       |
| A-07   | a07_auditoria_assurance.py     | Detectores forenses — 5 tipologias determinísticas    |
| A-08   | a08_auditor_nfa.py             | Análise qualitativa via LLM (fallback determinístico) |

### Detectores Forenses (A-07)

Todos são determinísticos — sem dependência de LLM:

- **CARROSSEL_FISCAL**: mesmo CNPJ aparece como emitente E destinatário
- **SMURFING_RURAL**: múltiplas notas abaixo do limiar de tributação no mesmo dia
- **FORNECEDOR_FANTASMA**: fornecedor com volume alto mas sem histórico recorrente
- **DEVOLUCAO_POSTERIOR**: nota de devolução emitida muito depois da original
- **ANOMALIA_TEMPORAL**: concentração de emissões em finais de semana ou feriados

---

## Módulo 2 — nfa_extractor

```
nfa_extractor/
├── domain/
│   ├── extractor.py           # v8.1.0: +cabecas, +destinatario_cpf, +regra_aplicada
│   ├── schemas.py
│   ├── constants.py
│   ├── nfa_ai_schemas.py
│   └── nfa_parser_ai.py
├── infrastructure/
│   ├── database_v2.py
│   ├── logging_config.py
│   ├── ai_client.py
│   ├── claude_validator.py    # NOVO v8.1.0
│   ├── audit_task_repo.py
│   └── supabase/
├── application/
│   ├── agents_engine.py
│   ├── analytics_engine.py
│   ├── audit_service.py
│   ├── extraction_orchestrator.py  # NOVO v8.1.0
│   └── sovereign_engine.py
└── utils/
    └── validators.py
```

---

## Módulo 3 — pdf_engine

Geração de relatórios fiscais em PDF via ReportLab.

---

## Módulo 4 — api

Backend FastAPI v8.0.0 unificado com JWT, rate limiting e pipeline NFA-e.

### Endpoints Principais

| Método | Rota                | Descrição                                     |
|--------|---------------------|-----------------------------------------------|
| POST   | /nfae               | Executa pipeline completo de auditoria NFA-e  |
| GET    | /resultado/{id}     | Recupera resultado de auditoria               |
| GET    | /relatorio/{id}/pdf | Download do relatório em PDF                  |
| POST   | /upload/{client_id} | Upload de PDFs para processamento em lote     |
| GET    | /status/{task_id}   | Status de processamento assíncrono            |
| POST   | /auth/login         | Autenticação JWT                              |
| GET    | /ping               | Health check                                  |
| GET    | /stats              | Estatísticas acumuladas do sistema            |

---

## Como Executar

### Backend

```bash
pip install fastapi uvicorn sqlalchemy pydantic anthropic xgboost numpy pdfplumber reportlab structlog tenacity
uvicorn api.main:app --host 127.0.0.1 --port 8082 --reload
```

### Frontend

```bash
cd frontend/frontend && npm install && npm run dev
```

---

## Variáveis de Ambiente

```env
ANTHROPIC_API_KEY=sk-ant-...
SQUAD_MODEL=anthropic:claude-sonnet-4-6
AUDITORIA_MODEL=anthropic:claude-sonnet-4-6
AUDITORIA_MODEL_SIMPLES=anthropic:claude-haiku-4-5-20251001
DATABASE_URL=sqlite:///./orgatec_sovereign.db
```

---

## Fluxo de Dados — Pipeline NFA-e

```
POST /nfae
├── RE-1 → Reclassifica VENDA para COMPRA rural (PF)
├── XGBoost → score 0–100 + nível BAIXO/MÉDIO/ALTO/CRÍTICO
├── F1-F6 → FUNRURAL + IRPF + resultado rural
├── A-07 → 5 detectores forenses determinísticos
└── A-08 → Análise qualitativa LLM + Protocolo @Delta
```

---

## Privacidade — Protocolo @Delta

Antes de enviar dados ao LLM, o `privacy.py` substitui CPF/CNPJ/nomes por tokens `@DELTA-001`, `@PESSOA-001`, `@EMPRESA-001`. O mapa de reversão é aplicado na resposta.

---

## Modo Degradado

Quando a API Claude está indisponível: A-07 e A-08 retornam `AgentResult(status="ERRO")`, o pipeline continua com score XGBoost + fiscal F1-F6 íntegros. Frontend exibe badge "IA DEGRADADO".

---

## Segurança

- JWT obrigatório em todas as rotas (exceto /ping, /, /auth/login)
- Rate limiting: 60 req/min por IP
- Protocolo @Delta: dados pessoais nunca trafegam para LLMs externos
- audit_hash SHA-256 em cada AgentResult

---

## Origem dos Módulos

| Módulo              | Origem                          | Observação                                         |
|---------------------|---------------------------------|----------------------------------------------------|
| horizon_blue_one/   | Worktree backend/               | Imports migrados backend.* → horizon_blue_one.*    |
| nfa_extractor/      | Projeto principal src/          | Imports migrados src.* → nfa_extractor.*           |
| pdf_engine/         | Projeto principal src/reports/  | Imports migrados                                   |
| api/                | Worktree api/                   | Serviços renomeados                                |
| frontend/           | Worktree frontend/              | Sem alteração de código                            |

---

## PRs de Melhoria — v8.1.0

| PR  | Fase | Título                                         | Status  |
|-----|------|------------------------------------------------|---------|
| #65 | P1-B | feat(extractor): campo cabecas + melhorias NFA | Merged  |
| #66 | P1-A | feat(application): ExtractionOrchestrator      | Merged  |
| #67 | P2-B | chore(deps): remover google-genai              | Merged  |
| #68 | P3-A | docs(ai_client): guia unificacao P3-A          | Merged  |
| #69 | P3-B | feat(infra): claude_validator                  | Merged  |
| #70 | P2-A | chore(scripts): archive_agents                 | Merged  |

---

Antes de enviar dados ao LLM, o `privacy.py` substitui CPF/CNPJ/nomes por tokens `@DELTA-001`, `@PESSOA-001`, `@EMPRESA-001`. O mapa de reversão é aplicado na resposta.
