# OrgAudi Sovereign — Plataforma de Auditoria Fiscal

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
├── ml/
│   └── xgboost_scorer.py        # 8 features × pesos SEFAZ-GO → score 0–100
│                                #   Modo heurístico quando modelo .pkl não está presente
└── orgaudi/
    ├── regra_especial_1.py      # RE-1: VENDA → COMPRA rural (aprovada CRC-GO)
    └── resumo_fiscal.py         # F1-F6: FUNRURAL 2026 (PJ=2.23%, PF=1.63%, SE=1.50%)
```

### Pipeline de Auditoria

| Etapa | Componente | Descrição |
|-------|-----------|-----------|
| RE-1 | `regra_especial_1.py` | Reclassifica VENDA em COMPRA rural para destinatário PF |
| Score | `xgboost_scorer.py` | Score de risco 0–100 com 8 features calibradas |
| Fiscal | `resumo_fiscal.py` | Apuração F1–F6: FUNRURAL, IRPF, resultado rural |
| A-07 | `a07_auditoria_assurance.py` | Detectores forenses — 5 tipologias determinísticas |
| A-08 | `a08_auditor_nfa.py` | Análise qualitativa via LLM (fallback determinístico) |

### Agentes — Resiliência

Ambos os agentes (A-07 e A-08) possuem `try/except` que retornam `AgentResult(status="ERRO")` caso a API Claude esteja indisponível. O pipeline nunca quebra por falha de LLM.

### Detectores Forenses (A-07)

Todos são **determinísticos** — sem dependência de LLM:

- **CARROSSEL_FISCAL**: mesmo CNPJ aparece como emitente E destinatário
- **SMURFING_RURAL**: múltiplas notas abaixo do limiar de tributação no mesmo dia
- **FORNECEDOR_FANTASMA**: fornecedor com volume alto mas sem histórico recorrente
- **DEVOLUCAO_POSTERIOR**: nota de devolução emitida muito depois da original
- **ANOMALIA_TEMPORAL**: concentração de emissões em finais de semana ou feriados

---

## Módulo 2 — nfa_extractor

Extração de PDFs e infraestrutura de dados.

```
nfa_extractor/
├── domain/
│   ├── extractor.py         # extrair_notas() — pdfplumber, regex, NFA dataclass
│   ├── schemas.py           # Pydantic v2: NotaFiscal, LoteAuditoria, ResultadoAuditoria
│   ├── constants.py         # CFOP rurais, limites tributários, enums
│   ├── nfa_ai_schemas.py    # Schemas para parser IA
│   └── nfa_parser_ai.py     # Parser NFA com Gemini/Claude
├── infrastructure/
│   ├── database_v2.py       # SQLAlchemy 2.0: Cliente, Laudo (SQLite)
│   ├── logging_config.py    # structlog com timestamp + nível + contexto
│   ├── ai_client.py         # Cliente unificado Anthropic/Gemini
│   ├── audit_task_repo.py   # Repositório de tarefas assíncronas
│   └── supabase/            # Integração Supabase (opcional)
├── application/
│   ├── agents_engine.py     # rodar_auditoria_completa() — orquestrador LangGraph
│   ├── analytics_engine.py  # processar_para_dataframe() — pandas/numpy
│   ├── audit_service.py     # Serviço de auditoria síncrono
│   └── sovereign_engine.py  # Motor soberano — coordenação de módulos
└── utils/
    └── validators.py        # Validação CPF, CNPJ, chave NF-e
```

### Modelos de Banco de Dados

```python
class Cliente(Base):
    id, nome, cpf, created_at

class Laudo(Base):
    id, cliente_id, resultado_json, score, created_at
```

---

## Módulo 3 — pdf_engine

Geração de relatórios fiscais em PDF.

```
pdf_engine/
├── orgaudi_v240/        # Motor v2.4.0 — relatório completo OrgAudi
│   ├── domain/          # Enums: TipoNota, RegimeTributario, Tipologia
│   ├── catalog/         # Catálogo de tipologias e regras
│   ├── data_processing/ # Processamento e agregação de dados
│   ├── handlers/        # Handlers por seção do relatório
│   ├── pages/           # Renderização de páginas PDF
│   ├── report_builder/  # Construtor principal do relatório
│   ├── styles/          # Estilos ReportLab
│   └── validators/      # Validação de dados de entrada
├── orgaudi_v250/        # Motor v2.5.0 — relatório simplificado
│   ├── renderer.py
│   ├── report_builder.py
│   └── template_builder.py
├── orgaudi_v4/          # Adaptador v4 para integração com HORIZON-BLUE
│   ├── orgaudi_adapter.py
│   ├── orgaudi_tipologias.py
│   └── orgaudi_v4.py
├── pdf_report.py        # Geração de laudo PDF via ReportLab (legacy)
├── ir_report.py         # Relatório IRPF rural
└── excel_export.py      # Export Excel via openpyxl
```

---

## Módulo 4 — api (Worktree)

Backend FastAPI v8.0.0 unificado.

```
api/
├── main.py              # Entry point — lifespan, middlewares, routers
├── middleware/
│   └── rate_limit.py    # 60 req/60s por IP
├── routes/
│   ├── auth.py          # JWT: /auth/login, /auth/register, /auth/me
│   ├── auditoria.py     # Pipeline NFA-e: /nfae, /resultado/{id}, /relatorio/{id}/pdf
│   ├── clientes.py      # CRUD clientes: /clientes
│   ├── agente.py        # Chat agente: /agente/chat
│   ├── nfa_ai_parser.py # Parser IA: /nfa/parse
│   ├── metrics.py       # Métricas internas
│   └── finance.py       # Endpoints financeiros
└── services/
    ├── auditoria_nfae.py    # Orquestrador HORIZON-BLUE ONE + geração de PDF
    └── auditoria_bigfour.py # Motor Big Four forense (triangulações, leilões, inventário)
```

### Endpoints Principais

| Método | Rota | Descrição |
|--------|------|-----------|
| `POST` | `/nfae` | Executa pipeline completo de auditoria NFA-e |
| `GET` | `/resultado/{id}` | Recupera resultado de auditoria |
| `GET` | `/relatorio/{id}/pdf` | Download do relatório em PDF |
| `POST` | `/nfae/relatorio` | Gera PDF direto a partir do payload |
| `POST` | `/upload/{client_id}` | Upload de PDFs para processamento em lote |
| `GET` | `/status/{task_id}` | Status de processamento assíncrono |
| `POST` | `/auth/login` | Autenticação JWT |
| `GET` | `/ping` | Health check |
| `GET` | `/stats` | Estatísticas acumuladas do sistema |

### Middlewares

- **RateLimitMiddleware**: 60 requisições por 60 segundos por IP
- **CORSMiddleware**: `localhost:5173–5175` com credentials

---

## Frontend

```
frontend/frontend/
├── src/
│   ├── pages/
│   │   ├── LoginPage.jsx        # Autenticação com animação Matrix
│   │   ├── Dashboard.jsx        # Painel principal com estatísticas
│   │   └── AuditoriaModule.jsx  # Módulo completo de auditoria NFA-e
│   ├── components/
│   │   └── MatrixBackground.jsx # Efeito visual chuva de código
│   ├── services/
│   │   └── api.js               # Axios + interceptor JWT
│   └── App.jsx                  # Router + ProtectedRoute
├── package.json                 # React 19, Framer Motion, Lucide, Tailwind v4
└── vite.config.js               # Proxy → :8082 (dev)
```

### Funcionalidades do AuditoriaModule

- Upload de notas fiscais (array JSON)
- Formulário: CPF, nome, regime (PF/PJ/Segurado Especial)
- Visualização de ScoreCard com nível de risco
- Painel "Detectores Forenses" (5 tipologias)
- Resumo Fiscal F1–F6 com valores monetários formatados
- Download de relatório PDF via endpoint `/relatorio/{id}/pdf`
- Indicador de status da IA (ATIVO / DEGRADADO)

---

## Banco de Dados

**Arquivo:** `orgatec_sovereign.db` (SQLite)

| Tabela | Colunas | Estado |
|--------|---------|--------|
| `clientes` | id, nome, cpf, created_at | 2 registros ativos |
| `laudos` | id, cliente_id, resultado_json, score, created_at | Limpo |

Sincronização automática via `Base.metadata.create_all(bind=engine)` no lifespan da API.

---

## Como Executar

### Pré-requisitos

```bash
Python 3.10+
Node.js 20+
```

### Backend

```bash
cd D:\01_Projetos_Ativos\OrgAudi

# Instalar dependências
pip install fastapi uvicorn sqlalchemy pydantic anthropic \
            xgboost numpy pdfplumber reportlab structlog tenacity

# Executar
uvicorn api.main:app --host 127.0.0.1 --port 8082 --reload
```

### Frontend

```bash
cd D:\01_Projetos_Ativos\OrgAudi\frontend\frontend

npm install
npm run dev   # :5173
```

### Variáveis de Ambiente

```env
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...          # opcional — Gemini parser
SQUAD_MODEL=anthropic:claude-sonnet-4-6
AUDITORIA_MODEL=anthropic:claude-sonnet-4-6
AUDITORIA_MODEL_SIMPLES=anthropic:claude-haiku-4-5-20251001
DATABASE_URL=sqlite:///./orgatec_sovereign.db
```

---

## Fluxo de Dados — Pipeline NFA-e

```
POST /nfae
    │
    ├── RE-1 (regra_especial_1.py)
    │     └── Reclassifica VENDA → COMPRA para destinatário PF rural
    │
    ├── XGBoost (xgboost_scorer.py)
    │     └── 8 features → score 0–100 + nível BAIXO/MÉDIO/ALTO/CRÍTICO
    │
    ├── F1-F6 (resumo_fiscal.py)
    │     └── FUNRURAL + IRPF + resultado rural
    │
    ├── A-07 (a07_auditoria_assurance.py)
    │     └── 5 detectores forenses determinísticos
    │
    └── A-08 (a08_auditor_nfa.py)
          └── Análise qualitativa LLM (fallback determinístico se API indisponível)
                └── Protocolo @Delta — CPF/CNPJ/nomes anonimizados antes do envio
```

---

## Privacidade — Protocolo @Delta

Antes de enviar qualquer dado ao LLM (Claude/Gemini), o `privacy.py` substitui:

- CPF/CNPJ reais → `@DELTA-001`, `@DELTA-002`, ...
- Nomes de pessoas → `@PESSOA-001`, `@PESSOA-002`, ...
- Razões sociais → `@EMPRESA-001`, `@EMPRESA-002`, ...

O mapa de reversão é mantido em memória e aplicado na resposta antes de retornar ao cliente.

---

## Modo Degradado

Quando a API Claude está indisponível (créditos zerados, timeout, etc.):

- A-07 retorna `AgentResult(status="ERRO", confidence=0.0)` com detalhe do erro
- A-08 idem — pipeline continua com score XGBoost + fiscal F1-F6 íntegros
- Frontend exibe badge "IA DEGRADADO" no módulo de auditoria
- Score e resumo fiscal são sempre produzidos (sem dependência de LLM)

---

## Segurança

- JWT obrigatório em todas as rotas (exceto `/ping`, `/`, `/auth/login`)
- Rate limiting: 60 req/min por IP
- CPF/CNPJ nunca trafegam em logs ou para LLMs externos (Protocolo @Delta)
- `.env` nunca versionado — secrets via variáveis de ambiente do OS
- `audit_hash` SHA-256 em cada `AgentResult` para rastreabilidade

---

## Origem dos Módulos

| Módulo | Origem | Observação |
|--------|--------|-----------|
| `horizon_blue_one/` | Worktree `backend/` | Imports migrados `backend.*` → `horizon_blue_one.*` |
| `nfa_extractor/` | Projeto principal `src/` | Imports migrados `src.*` → `nfa_extractor.*` |
| `pdf_engine/` | Projeto principal `src/application/reports/` | Imports migrados |
| `api/` | Worktree `api/` | Serviços renomeados: `auditoria_nfae.py`, `auditoria_bigfour.py` |
| `frontend/` | Worktree `frontend/` | Sem alteração de código |

---

*OrgAudi Sovereign Shield — ORGATEC v8.0.0*
