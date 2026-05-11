# OrgAudi Sovereign — Plataforma de Auditoria Fiscal

**Versão:** 8.0.0  
**Stack:** FastAPI · React 19 · Claude Opus/Sonnet/Haiku · XGBoost · LSTM · MCP · SQLite · ReportLab  
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

Squad consolidado de 7 agentes (S1–S7) coordenados por `Orchestrator` com EventBus, pré-cálculo determinístico, gate por probabilidade de autuação e roteamento de modelos Haiku/Sonnet/Opus (mix 90/8/2).

```
horizon_blue_one/
├── agents/
│   ├── base_agent.py        # AgentResult (Pydantic v2, SHA-256 audit_hash)
│   ├── s1_sentinel.py       # @Sentinel — LGPD + ZeroTrust + integridade documental
│   ├── s2_forense.py        # @Forense — detectores + XGBoost + LSTM + MCP tools
│   ├── s3_fiscal.py         # @Fiscal — ICMS, ITR, LCDPR, CFOP
│   ├── s4_contabil.py       # @Contábil — patrimônio, biológicos (CPC 29), caixa
│   ├── s5_nfa.py            # @AuditorNFA — auditoria de notas RE-1 aplicada
│   ├── s6_rh.py             # @RH — eSocial, FGTS, INSS
│   ├── s7_ceo.py            # @CEO — governança, parecer jurídico, MD&A
│   ├── detectores_forenses.py   # CARROSSEL, SMURFING, FORNECEDOR_FANTASMA,
│   │                            #   DEVOLUCAO_POSTERIOR, ANOMALIA_TEMPORAL
│   └── _legacy/             # 28 agentes A-00..A-27 preservados (rollback/regressão)
├── core/
│   ├── orchestrator.py      # EventBus + paralelo asyncio + pf-gate + early-exit
│   ├── precalc.py           # Pré-cálculo determinístico injetado no payload
│   ├── token_router.py      # Roteamento 90/8/2 com upgrade/downgrade por critério
│   ├── model_adapter.py     # Claude Haiku/Sonnet/Opus + tool_use (MCP)
│   ├── privacy.py           # Protocolo @Delta — anonimização CPF/CNPJ/nomes
│   ├── limiares.py          # Thresholds centralizados (calibração CRC-GO)
│   └── ledger.py            # Audit log assíncrono
├── ml/
│   ├── xgboost_scorer.py    # 8 features × pesos SEFAZ-GO → score 0–100
│   └── lstm_scorer.py       # Anomalia temporal (heurístico + PyTorch opcional)
├── tools/
│   └── mcp_bridge.py        # Model Context Protocol — histórico produtor + fetch HTTP
├── nfa_bridge/              # Bridge nfa-repo → precalc (CFOP heurístico + RE-1)
└── orgaudi/
    ├── regra_especial_1.py  # RE-1: VENDA → COMPRA rural (aprovada CRC-GO)
    └── resumo_fiscal.py     # F1-F6: FUNRURAL 2026 (PJ=2.23%, PF=1.63%, SE=1.50%)
```

### Pipeline S1–S7

| Etapa | Agente | Tarefa | Modelo padrão |
|-------|--------|--------|---------------|
| S1 | @Sentinel | LGPD + integridade documental | Haiku |
| S2 | @Forense | XGBoost + LSTM + 5 detectores + MCP | Sonnet |
| S3 | @Fiscal | ICMS, ITR, LCDPR, CFOP | Haiku |
| S4 | @Contábil | Patrimônio, CPC 29, caixa | Haiku |
| S5 | @AuditorNFA | Auditoria das notas (RE-1 aplicada) | Sonnet (↓Haiku se score<50) |
| S6 | @RH | eSocial, FGTS, INSS | Haiku |
| S7 | @CEO | Consolidação, parecer jurídico, MD&A | Sonnet (↑Opus se crítico) |

### Orchestrator — controle de custo

- **Pré-cálculo determinístico**: `precalc.py` roda uma vez em paralelo (XGBoost + LSTM + CFOP + LCDPR + ITR + detectores), injetado no payload de todos os agentes.
- **Early-exit**: caso limpo (score<30, zero detecções, CFOP/LCDPR conformes) retorna sem chamar LLM.
- **pf-gate**: probabilidade de autuação determinística filtra o pipeline:
  - `pf < 0.40` → arquivado sem LLM
  - `pf < 0.65` → só S3 + S5 + S7
  - `pf < 0.85` → S1 + S2 + S3 + S5 + S7 (sem S4/S6)
  - `pf >= 0.85` → pipeline completo
- **Paralelismo**: agentes independentes rodam via `asyncio.gather`.
- **Budget de tokens**: corta o pipeline se exceder o orçamento configurado.

### Detectores Forenses (S2 @Forense)

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

## Fluxo de Dados — Pipeline S1–S7

```
POST /auditoria
    │
    ├── precalc.py (paralelo asyncio.gather, UMA vez)
    │     ├── RE-1 — reclassifica VENDA → COMPRA destinatário rural
    │     ├── XGBoost — 8 features → score 0–100 + nível
    │     ├── LSTM — anomalia temporal por produtor (σ=2.5)
    │     ├── CFOP — divergências e total
    │     ├── LCDPR — receita_notas vs receita_lcdpr
    │     ├── ITR — área total/utilizada → GU%
    │     ├── Detectores forenses (5 tipologias)
    │     └── PII — total_pii + redação @Delta
    │
    ├── Orchestrator
    │     ├── early-exit → arquiva sem LLM se audit limpa
    │     ├── pf-gate → reduz pipeline conforme prob. de autuação
    │     └── asyncio.gather S1..S6 em paralelo
    │
    └── S7 @CEO (sempre executa por último)
          └── consolida outputs + parecer jurídico + MD&A
                └── Protocolo @Delta aplicado em todos os prompts
```

---

## Privacidade — Protocolo @Delta

Antes de enviar qualquer dado ao LLM (Claude), `core/privacy.py` substitui:

- CPF/CNPJ reais → `[CPF_PROTEGIDO]` / `[CNPJ_PROTEGIDO]`
- Campos `nome`, `razao_social`, `proprietario`, `remetente_nome`, `destinatario_nome` → `[NOME_REDACTED_<tamanho>]`
- Estruturas aninhadas (dict/lista) processadas recursivamente

Aplicado em `anonymize_payload()` antes de qualquer `call_otimizado()`.

---

## MCP — Model Context Protocol

Quando S2 @Forense detecta anomalia temporal (LSTM score ≥ 0.70), o agente recebe acesso a duas ferramentas via tool_use:

- **`consultar_historico_produtor(cnpj_cpf, ano)`** — query SQLite read-only ao histórico interno
- **`buscar_dados_externos(url)`** — GET HTTP com allowlist estrita (sefazgo.gov.br, nfe.fazenda.gov.br, receita.fazenda.gov.br, cadin.fazenda.gov.br, cidades.ibge.gov.br)

Tudo registrado em `audit_events` com hash + timestamp.

---

## Modo Degradado

Quando a API Claude está indisponível (créditos zerados, timeout, etc.):

- Todos os agentes possuem fallback determinístico — pipeline nunca quebra
- `precalc` produz score + detectores + classificações sem nenhuma chamada LLM
- Apenas o parecer qualitativo de S7 fica vazio; demais outputs íntegros
- Frontend exibe badge "IA DEGRADADO" no módulo de auditoria

---

## Segurança

- JWT obrigatório (HS256, 30 min access + 7 d refresh)
- Rate limiting: 60 req/min por IP
- Body size limit: 10 MB (configurável `MAX_BODY_SIZE_MB`)
- Security headers: HSTS (prod), CSP, X-Frame-Options DENY, X-Content-Type-Options nosniff, Referrer-Policy strict-origin-when-cross-origin, Permissions-Policy bloqueia câmera/mic/geo
- CORS estrito: métodos e headers específicos; origens controladas por `ALLOWED_ORIGINS`
- CPF/CNPJ nunca trafegam em logs ou para LLMs externos (Protocolo @Delta)
- `.env` nunca versionado — secrets via variáveis de ambiente do OS
- `audit_hash` SHA-256 em cada `AgentResult` para rastreabilidade
- CI: TruffleHog (`--only-verified --fail`), ruff, mypy, pip-audit

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
