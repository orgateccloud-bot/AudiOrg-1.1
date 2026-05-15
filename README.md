# OrgAudi — Plataforma de Auditoria Fiscal

**Versão:** 1.0.0  
**Pilha:** FastAPI · React 19 · LangGraph · Claude/Gemini · XGBoost · SQLite · ReportLab  
**Responsável:** ORGATEC IA

---

## Visão Geral

OrgAudi é a plataforma unificada de auditoria de Notas Fiscais Avulsas (NFA-e) da ORGATEC. Integra extração de PDF, pipeline analítico determinístico, agentes de IA e geração de relatórios em um único sistema multi-módulo.

O projeto consolida três bases de código anteriores (NFA Extractor, Horizon-Blue e worktree `great-hypatia`) em uma estrutura limpa de quatro módulos.

---

## Arquitetura — 4 Módulos

```
OrgAudi/
├── horizonte_azul_um/      # Pipeline de auditoria HORIZON-BLUE ONE
├── extrator nfa/           # Extração de PDF e infraestrutura de dados
├── pdf_engine/             # Geração de relatórios OrgAudi
├── relatórios_nfa/         # Templates e ativos de relatório
├── API/                    # FastAPI — Backend unificado
├── front-end/              # React 19 + Vite + Tailwind v4
├── alambique/              # Migrações Alembic
├── k8s/                    # Manifests Kubernetes
├── dados/                  # Dados versionados (alíquotas FUNRURAL etc.)
├── documentos/             # Documentação técnica
├── roteiros/               # Scripts utilitários
├── testes/                 # Suíte de testes
└── orgatec_sovereign.db    # SQLite — clientes e laudos
```

---

## Módulo 1 — horizonte_azul_um

Pipeline sequencial de auditoria fiscal: **RE-1 → XGBoost → F1-F6 → A-07 → A-08**

```
horizonte_azul_um/
├── agents/
│   ├── base_agent.py            # AgentResult (Pydantic v2, SHA-256 audit_hash)
│   ├── a07_auditoria_assurance.py
│   ├── a08_auditor_nfa.py
│   └── detectores_forenses.py
├── core/
│   ├── config.py
│   ├── model_adapter.py         # Claude Sonnet / Haiku / Opus + retry com tenacity
│   └── privacy.py               # Protocolo @Delta — anonimização CPF/CNPJ/nomes
├── ml/
│   └── xgboost_scorer.py        # 8 features × pesos SEFAZ-GO → score 0–100
└── orgaudi/
    ├── regra_especial_1.py      # RE-1: VENDA → COMPRA rural (aprovada CRC-GO)
    └── resumo_fiscal.py         # F1-F6: FUNRURAL 2026
```

### Pipeline de Auditoria

| Etapa  | Componente                  | Descrição                                                   |
|--------|-----------------------------|-------------------------------------------------------------|
| RE-1   | regra_especial_1.py         | Reclassifica VENDA em COMPRA rural para destinatário PF     |
| Score  | xgboost_scorer.py           | Score de risco 0–100 com 8 features calibradas              |
| Fiscal | resumo_fiscal.py            | Apuração F1–F6: FUNRURAL, IRPF, resultado rural             |
| A-07   | a07_auditoria_assurance.py  | Detectores forenses — 5 tipologias determinísticas          |
| A-08   | a08_auditor_nfa.py          | Análise qualitativa via LLM (com fallback determinístico)   |

### Detectores Forenses (A-07)

Todos são determinísticos — sem dependência de LLM:

- **CARROSSEL_FISCAL**: mesmo CNPJ aparece como emitente E destinatário.
- **SMURFING_RURAL**: múltiplas notas abaixo do limiar de tributação no mesmo dia.
- **FORNECEDOR_FANTASMA**: fornecedor com volume alto, sem histórico recorrente.
- **DEVOLUCAO_POSTERIOR**: nota de devolução emitida muito depois da original.
- **ANOMALIA_TEMPORAL**: concentração de emissões em finais de semana ou feriados.

---

## Módulo 2 — extrator nfa

```
extrator nfa/
├── domain/
│   ├── extractor.py             # Campos: cabeças, destinatario_cpf, regra_aplicada
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

Backend FastAPI unificado com JWT, rate limiting e pipeline NFA-e.

### Endpoints Principais

| Método | Rota                 | Descrição                                       |
|--------|----------------------|-------------------------------------------------|
| POST   | /nfae                | Executa pipeline completo de auditoria NFA-e    |
| GET    | /resultado/{id}      | Recupera resultado de auditoria                 |
| GET    | /relatorio/{id}/pdf  | Download do relatório em PDF                    |
| POST   | /upload/{client_id}  | Upload de PDFs para processamento em lote       |
| GET    | /status/{task_id}    | Status de processamento assíncrono              |
| POST   | /auth/login          | Autenticação JWT                                |
| GET    | /ping                | Health check                                    |
| GET    | /stats               | Estatísticas acumuladas do sistema              |

---

## Como Executar

### Backend

```bash
pip install fastapi uvicorn sqlalchemy pydantic anthropic xgboost numpy \
            pdfplumber reportlab structlog tenacity
uvicorn api.main:app --host 127.0.0.1 --port 8082 --reload
```

### Front-end

```bash
cd front-end && npm install && npm run dev
```

### Variáveis de Ambiente

```env
ANTHROPIC_API_KEY=sk-ant-...
SQUAD_MODEL=anthropic:claude-sonnet-4-6
AUDITORIA_MODEL=anthropic:claude-sonnet-4-6
AUDITORIA_MODEL_SIMPLES=anthropic:claude-haiku-4-5-20251001
DATABASE_URL=sqlite:///./orgatec_sovereign.db
```

Veja `.env.exemplo` na raiz para a lista completa.

---

## Fluxo de Dados — Pipeline NFA-e

```
POST /nfae
 ├── RE-1     → Reclassifica VENDA para COMPRA rural (PF)
 ├── XGBoost  → score 0–100 + nível BAIXO/MÉDIO/ALTO/CRÍTICO
 ├── F1-F6    → FUNRURAL + IRPF + resultado rural
 ├── A-07     → 5 detectores forenses determinísticos
 └── A-08     → Análise qualitativa LLM + Protocolo @Delta
```

---

## Privacidade — Protocolo @Delta

Antes de enviar dados ao LLM, `privacy.py` substitui CPF/CNPJ/nomes por tokens `@DELTA-001`, `@PESSOA-001`, `@EMPRESA-001`. O mapa de reversão é aplicado na resposta.

---

## Modo Degradado

Quando a API Claude está indisponível: A-07 e A-08 retornam `AgentResult(status="ERRO")`, o pipeline continua com score XGBoost e fiscal F1-F6 íntegros. O front-end exibe o emblema **"IA DEGRADADO"**.

---

## Segurança

- JWT obrigatório em todas as rotas (exceto `/ping`, `/`, `/auth/login`).
- Rate limiting: 60 requisições/min por IP.
- Protocolo @Delta: dados pessoais nunca trafegam para LLMs externos.
- `audit_hash` SHA-256 em cada `AgentResult`.

Detalhes em `SEGURANÇA.md`.

---

## Governança do Projeto

- **Licença**: ver `LICENÇA`.
- **Contribuição**: ver `CONTRIBUINDO.md`.
- **Catálogo de agentes**: ver `CATÁLOGO_DE_AGENTES.md`.
- **Integração / onboarding**: ver `INTEGRAÇÃO.md` e `CLAUDE.md`.
- **Score de qualidade**: ver `ATUALIZADO_SCORE_9.0.md`.
- **Migrações de banco**: Alembic em `alambique/` (`alembic.ini` na raiz).
- **Docker**: `docker-compose.yml` (Redis + serviços).
- **Pré-commit**: `.pre-commit-config.yaml` (ruff, mypy, bandit).
