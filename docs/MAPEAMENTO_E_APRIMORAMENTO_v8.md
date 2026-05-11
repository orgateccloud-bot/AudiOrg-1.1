# Mapeamento Completo & Relatório de Aprimoramento — OrgAudi Sovereign v8.0.0

> **Data:** 2026-05-11
> **Versão analisada:** v8.0.0 (commit `790842f`)
> **Escopo:** repositório [orgateccloud-bot/AudiOrg-1.1](https://github.com/orgateccloud-bot/AudiOrg-1.1), branch `main`.

Documento técnico produzido a partir de varredura completa do código, das dependências e dos arquivos de configuração. Mapeia arquitetura, agentes e tecnologias do v8.0.0 e propõe melhorias priorizadas em buckets **P0/P1/P2/P3** com quick-wins e anti-recomendações.

---

## 1. Arquitetura (4 módulos)

```
┌─────────────────────────────────────────────────────────────┐
│ FRONTEND  React 19 + Vite 8 + Tailwind 4 + React Router 7    │
└──────────────────────────┬──────────────────────────────────┘
                           │ REST + JWT (HS256, TTL 60min)
┌──────────────────────────▼──────────────────────────────────┐
│ api/           FastAPI v8.0.0                                │
│   routes:  auth, auditoria, clientes, agente (sempre)        │
│           + metrics, finance, nfa_ai_parser (try/except!)    │
│   middleware: rate_limit (60req/60s, in-memory), CORS        │
│   services:   auditoria_nfae, auditoria_bigfour              │
└─────┬──────────────────┬─────────────────────┬──────────────┘
      │                  │                     │
┌─────▼──────────┐ ┌─────▼─────────────┐ ┌────▼─────────────┐
│ horizon_blue_  │ │ nfa_extractor/    │ │ pdf_engine/      │
│   one/         │ │   domain/         │ │ orgaudi_v240/    │
│   30 agents    │ │   infrastructure/ │ │ orgaudi_v250/    │
│   (A-00..A-27, │ │   application/    │ │ orgaudi_v4/      │
│    a_token)    │ │   utils/          │ │ pdf_report.py    │
│   detectores_  │ │                   │ │ ir_report.py     │
│   forenses     │ │                   │ │ excel_export.py  │
│   ml/xgboost   │ │                   │ │ (3 versões!)     │
│   orgaudi/     │ │                   │ │                  │
│     RE-1,F1-F6,│ │                   │ │                  │
│     AN-01..18  │ │                   │ │                  │
│   core/        │ │                   │ │                  │
│     token_     │ │                   │ │                  │
│     router 10K │ │                   │ │                  │
└────────────────┘ └───────────────────┘ └──────────────────┘
                           │
                ┌──────────┼──────────┐
                │          │          │
        SQLAlchemy 2.0  Anthropic   Supabase
        + SQLite        Claude API  (opcional)
        (Alembic)       (Sonnet/    finance/*
                         Haiku/Opus)
```

**Fluxo de auditoria NFA-e:**
```
PDF NFA-e
  └─► pdfplumber/PyMuPDF → schema NotaFiscal (Pydantic v2)
     └─► RE-1 (regra_especial_1) — reclassifica VENDA→COMPRA rural PF
        └─► XGBoost Scorer — score 0-100 (carimba score_origem="xgboost_scorer")
           └─► F1-F6 Resumo Fiscal — FUNRURAL 2026, IRPF estimado
              └─► A-07 Assurance — 5 detectores determinísticos + Claude opcional
                 └─► A-08 Auditor-NFA — qualitativo Claude + Protocolo @Delta
                    └─► A-00 CEO — decisão final (verifica score_origem)
                       └─► pdf_engine/orgaudi_v* → PDF laudo
```

---

## 2. Agentes — A Camada de Orquestração Unificada

Os 30 agentes existem como arquivos separados, mas **três agentes pivô orquestram tudo**:

### 2.1. Os três agentes-pivô

| Pivô       | Função                                                                                    | Hardenings ativos                                                                                                                  |
|------------|-------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------|
| **A-01 @Junior** | Manager Router. Recebe `tipo_analise` + contexto e decide qual agente especializado executa, via Haiku. Grava ledger persistente com `requisicao_id` (UUID v4) e `audit_hash` SHA-256. | `AGENTES_VALIDOS` (frozenset) — destino retornado pelo LLM é validado contra registry; rejeita injeção de IDs arbitrários. Fallback por família quando `tipo_analise` é desconhecido. |
| **A-Token @Token** | Roteador econômico de modelo Claude. Decide Haiku/Sonnet/Opus por `score_risco`, `tipologias_criticas`, `probabilidade_autuacao`, `num_notas`. Mantém estatísticas de uso e projeção mensal de custo. | Lógica em `core/token_router.py` (10.8 KB).                                                                                       |
| **A-00 @CEO**    | Governança final. Aprova/rejeita/escala resultado dos demais agentes. Seleciona Opus apenas para casos críticos.                                                                          | `ORIGEM_SCORE_CONFIAVEL = {"xgboost_scorer","a07_assurance","internal"}` — score injetado por cliente externo é desconsiderado (anti prompt-injection). Confiança de fallback agora é 0.0 (corrige bug em que era 0.9 enganoso). |

### 2.2. Roteamento dinâmico no A-01

```
"nfa","rural"   → A-08   "icms"      → A-21   "itr"          → A-22
"biologicos"    → A-26   "cfop"      → A-24   "lcdpr"        → A-25
"anomalias"     → A-23   "forense"   → A-27   "contabil"     → A-19
"esocial"       → A-20   "sped"      → A-05   "tributaria"   → A-11
"juridica"      → A-15   "fraude"    → A-12   "caixa"        → A-17
"conformidade"  → A-13   "patrimonio"→ A-10   "risco"        → A-14
"lgpd"          → A-16   "csuite"    → A-18
```

### 2.3. Os 30 agentes especializados

| ID    | Classe                       | Função                                                          |
|-------|------------------------------|-----------------------------------------------------------------|
| A-00  | CEOAgent                     | Governança final (anti-injection: `score_origem`)               |
| A-01  | JuniorAgent                  | **Manager Router** (Haiku) com `AGENTES_VALIDOS`                |
| A-02  | ProtetorAgent                | Proteção genérica contra fraudes                                |
| A-03  | ZeroTrustAgent               | Validação zero-trust de autenticidade                           |
| A-04  | VigilanteAgent               | Monitoramento contínuo                                          |
| A-05  | EngenheiroERPAgent           | Integração ERP / SPED                                           |
| A-06  | ExtratorFaturasAgent         | Extração de faturas (delega para `nfa_extractor`)               |
| **A-07** | **AuditoriaAssuranceAgent** | **5 detectores determinísticos + XGBoost + Claude (opcional)**  |
| **A-08** | **AuditorNFAAgent**         | **Qualitativo Claude + Protocolo @Delta**                        |
| A-09  | AuditorTIAgent               | TI                                                              |
| A-10  | AuditorPatrimonioAgent       | Patrimônio                                                      |
| A-11  | PlanejadorTributarioAgent    | Planejamento tributário                                          |
| A-12  | DescobridorDeducoesAgent     | Deduções (`fraude` → A-12)                                       |
| A-13  | MonitorConformidadeAgent     | Conformidade                                                     |
| A-14  | AvaliadorRiscoAgent          | Risco                                                            |
| A-15  | JuridicoExtAgent             | Jurídico                                                         |
| A-16  | LGPDAgent                    | LGPD                                                             |
| A-17  | PrevisorCaixaAgent           | Fluxo de caixa                                                   |
| A-18  | AnalistaCsuiteAgent          | C-Suite                                                          |
| A-19  | ContabilistaIAAgent          | Contábil                                                         |
| A-20  | EsocialIAAgent               | e-Social                                                         |
| A-21  | AuditorICMSAgent             | ICMS                                                             |
| A-22  | AuditorITRAgent              | ITR                                                              |
| A-23  | AnalistaAnomaliasAgent       | Anomalias AN-01..AN-18                                          |
| A-24  | ClassificadorCFOPAgent       | CFOP                                                             |
| A-25  | AuditorLCDPRAgent            | LCDPR                                                            |
| A-26  | AuditorBiologicosAgent       | Ativos biológicos                                                |
| A-27  | EpsilonAgent                 | Forense avançado (grafo de conluio)                              |
| A-Token | TokenAgent                  | **Otimizador de modelo Claude**                                  |

**Detectores forenses A-07 (determinísticos, sem LLM):** `CARROSSEL_FISCAL`, `SMURFING_RURAL`, `FORNECEDOR_FANTASMA`, `DEVOLUCAO_POSTERIOR`, `ANOMALIA_TEMPORAL`.

**Catálogo de Anomalias AN-01 a AN-18:** smurfing, carrossel, nota fria, sub/superfaturamento, CFOP indevido, trânsito não realizado, transferência intrafamiliar, IE inativa, período suspeito, volume incompatível, caixa dois, concentração atípica, devolução sistemática, Funrural subdeclarado, ITR divergente, sobreposição de períodos, ausência de GTA.

### 2.4. BaseAgent (interface comum)

- `async def process(payload) -> AgentResult` (abstrato)
- `AgentResult`: `agent_id`, `status` ∈ {APROVADO, REJEITADO, ESCALADO, ERRO}, `output`, `confidence`, `timestamp`, `audit_hash` (SHA-256, truncado para `settings.AUDIT_HASH_LEN` ou 64)
- Helpers: `log()`, `log_error()`, `parse_json_response()`, `derivar_confidence()`
- Retry: `tenacity` 3×, backoff exponencial 1–8s (no `model_adapter`)

---

## 3. Tecnologias

| Camada            | Stack                                                                    | Versão        |
|-------------------|--------------------------------------------------------------------------|---------------|
| Frontend          | React + Vite + Tailwind + React Router + Axios + Framer Motion + Lucide  | 19.2 / 8.0 / 4.2 / 7.14 |
| API               | FastAPI + Uvicorn + Pydantic v2 + python-multipart                       | 0.104+ / 0.24+ |
| Auth              | python-jose (JWT HS256) + passlib + bcrypt                                | 3.3+ / 1.7.4 / <4.0 |
| DB                | SQLAlchemy 2.0 + Alembic + SQLite (dev) / PostgreSQL via psycopg2 + Supabase | 2.0+ / 1.x / 2.0+ |
| LLM               | anthropic SDK (Claude) + google-genai (Gemini opcional)                  | 0.49+ / 0.2+ |
| Orquestração      | LangGraph (legado Sigma/Gama/Auditor)                                    | 0.1.0 — antigo |
| Roteamento modelo | `core/token_router.py` (próprio, 10.8KB)                                 | custom        |
| ML                | xgboost + scikit-learn + pandas + numpy                                  | 2.1+ / 1.3+ / 2.0+ |
| PDF               | pdfplumber + PyMuPDF + reportlab + openpyxl + Pillow + matplotlib        | 0.10+ / 1.24+ / 4.0+ |
| Logging           | structlog + tenacity + defusedxml                                        | 24.0+ / 9.0+ |
| Resiliência       | Circuit breaker in-memory (`ai_client._CircuitState`) + retry tenacity   | —             |
| Privacidade       | Protocolo @Delta (anonimiza CPF/CNPJ/nomes pré-LLM)                      | custom (1KB)  |
| CI/CD             | GitHub Actions: pytest (3.10/3.11/3.12) + frontend build + TruffleHog    | —             |
| Tests             | pytest (~40 arquivos, ~40-60% cobertura geral, ~20-30% em regras fiscais) | —             |

**Variáveis de ambiente críticas** (`.env.example`): `ANTHROPIC_API_KEY`, `SQUAD_MODEL`, `AUDITORIA_MODEL`, `AUDITORIA_MODEL_SIMPLES`, `DATABASE_URL`, `SUPABASE_*`, `JWT_SECRET_KEY`, `XGBOOST_MODEL_PATH`, `REPORT_LANG`, `LOG_LEVEL`.

**Achados de risco:**

1. **`api/main.py` linhas 71-77** — silent failure: `try/except: pass` engole erros de import de `metrics`, `finance`, `nfa_ai_parser`. Endpoints inteiros desaparecem sem log.
2. **`api/routes/auditoria.py` linha 48-61** — endpoint `/upload/{client_id}` recebe `List[UploadFile]` sem limite de tamanho/MIME/magic-bytes.
3. **`api/main.py` linhas 57-60** — origens CORS hardcoded para `localhost:5173-5175`.
4. **`api/services/auditoria_nfae.py`** — `tasks_status`, `resultados_store` mantidos em dicts in-memory.
5. **`horizon_blue_one/agents/a01_junior.py`** — `_ledger: list = []` na classe; perdido em restart.

**O que NÃO existe no repo (e talvez devesse):**
- Dockerfile, docker-compose.yml
- ruff.toml, mypy.ini, .pre-commit-config.yaml
- tsconfig.json (frontend, apesar de usar `@types/react`)
- prettier, biome
- vitest/jest (frontend sem teste)
- OpenTelemetry / Prometheus exporters
- Runbook de deploy / `.env` de staging

---

## 4. Recomendações Priorizadas

### P0 — Bloqueia produção segura (resolver antes do próximo fechamento fiscal)

| #  | Item                                                              | Por quê                                                                                       |
|----|-------------------------------------------------------------------|-----------------------------------------------------------------------------------------------|
| P0-1 | Validar tamanho/MIME/magic-bytes do upload PDF                    | Endpoint público sem limite = DoS trivial + vetor de PDF malicioso. 2h.                       |
| P0-2 | Persistir `tasks_status` e `resultados_store` em Redis/Postgres   | Restart no meio de uma task = laudo perdido no fechamento. Risco LGPD por dado órfão.         |
| P0-3 | Mover rate limit para Redis                                       | In-memory é furado por restart e multi-instância.                                              |
| P0-4 | Cobertura de testes RE-1, F1-F6, AN-01 a AN-18                   | ~30% em regras que produzem o veredito. Bug em F4 (Funrural PJ 2.23%) afeta TODOS os PJ.       |
| P0-5 | Log append-only de des-anonimização @Delta                         | LGPD Art. 37: quem viu qual CPF/CNPJ real, quando, com qual prompt. Hoje não há trilha.       |
| P0-6 | Hash SHA-256 do PDF emitido salvo no banco                         | PDF é evidência jurídica. Sem checksum no momento da emissão, não há prova de integridade.    |
| P0-7 | Substituir `try/except: pass` em `api/main.py:71-77` por log estruturado | Silent failure faz endpoints inteiros desaparecerem sem alerta. 15 min de fix.            |

### P1 — Próximo ciclo (4-8 semanas)

| #  | Item                                                              | Por quê                                                                                       |
|----|-------------------------------------------------------------------|-----------------------------------------------------------------------------------------------|
| P1-1 | Externalizar alíquotas FUNRURAL para YAML versionado              | Alíquotas mudam por ato normativo durante o ano. Hoje cada mudança vira deploy de código.     |
| P1-2 | Revogação de refresh token (`jti` + blacklist Redis)              | Token vazado de auditor não tem kill switch.                                                  |
| P1-3 | Migrar passlib+bcrypt<4.0 → argon2-cffi ou pwdlib                 | passlib é abandonware; pin de bcrypt é dívida que cresce.                                     |
| P1-4 | SQLite → PostgreSQL em produção                                   | Trava acima de ~10 escritas/s; sem PITR; sem RLS para multi-tenant rural.                     |
| P1-5 | Fixtures determinísticas para os 5 detectores de A-07              | Hoje testados só em fallback de erro. Regressão silenciosa é certeza.                          |
| P1-6 | Sentry + 4 métricas Prometheus (laudos/h, p95, erro A-08, $token/dia) | `/tokens` e `/metrics/ai` já existem mas não exportam Prometheus.                            |
| P1-7 | Persistir ledger do A-01 fora de `_ledger: list = []` in-memory    | `a01_junior.py` mantém ledger em variável de classe — perdido no restart. Tabela `auditoria_ledger`. |
| P1-8 | Persistir `get_stats()` do `token_router` em Postgres              | Stats de custo Claude resetam no restart, impossibilitando rastreio mensal.                   |

### P2 — Próximo trimestre

| #  | Item                                                              | Por quê                                                                                       |
|----|-------------------------------------------------------------------|-----------------------------------------------------------------------------------------------|
| P2-1 | ruff + black + pre-commit                                          | Acelera todo o resto. 1 dia.                                                                  |
| P2-2 | Dockerfile + docker-compose                                        | Onboarding e ambiente reproduzível.                                                            |
| P2-3 | CORS via env var (hoje hardcoded localhost:5173-5175 em `main.py`) | Bloqueia deploy em staging/prod.                                                              |
| P2-4 | Frontend backend URL via `VITE_API_URL` (hoje `:8082` hardcoded)   | Mesmo motivo.                                                                                  |
| P2-5 | Versionamento de prompts LLM (`prompts/` com hash em cada chamada) | Mudança silenciosa de prompt pode mudar veredito de auditoria.                                |
| P2-6 | tsconfig.json no frontend                                          | Já usa `@types/react` — falta config explícita.                                               |
| P2-7 | Documentar uso real dos 30 agentes (A-02..A-06, A-09..A-20)        | Maioria não aparece no fluxo principal. São dead code? Stubs?                                 |

### P3 — Adiar conscientemente

| #  | Item                                                              | Por quê adiar                                                                                 |
|----|-------------------------------------------------------------------|-----------------------------------------------------------------------------------------------|
| P3-1 | Consolidar pdf_engine v240/v250/v4                                 | Refactor cego é mais arriscado que o débito. Só após snapshot tests (P3-2).                   |
| P3-2 | Snapshot tests de PDF gerado                                       | Pesado; só vale quando atacar P3-1.                                                            |
| P3-3 | Upgrade LangGraph 0.1 → 0.3                                        | Breaking changes; só após A-07/A-08 com cobertura >70%.                                       |
| P3-4 | Integração CEPEA real (AN-04/AN-05)                                | Depende de contrato CEPEA-USP. Decisão de produto, não de eng.                                |
| P3-5 | Testes frontend (vitest)                                           | Adicionar quando o frontend mudar substancialmente.                                            |
| P3-6 | OpenTelemetry completo                                             | Sentry + 4 métricas resolvem 80% com 10% do esforço.                                          |

### Quick-wins (<1 dia cada, ROI alto)

1. **Fix do silent `try/except: pass` em `api/main.py:71-77`** (P0-7) — 15 minutos.
2. **Validação upload PDF** (P0-1) — 2h, fecha DoS.
3. **Hash SHA-256 do PDF emitido** (P0-6) — 2h, fecha gap de integridade jurídica.
4. **ruff + pre-commit** (P2-1) — meio dia, destrava todo o resto.
5. **CORS via env + backend URL via env** (P2-3, P2-4) — 1h.
6. **YAML de alíquotas Funrural** (P1-1) — meio dia.

### Anti-recomendações (NÃO fazer agora)

- **Não consolidar `pdf_engine/v240/v250/v4`** sem snapshot tests — risco de quebrar laudos em produção.
- **Não atualizar LangGraph 0.1 → 0.3** antes de A-07/A-08 com cobertura >70%.
- **Não reduzir o número de agentes** (A-09 a A-20). Apesar de parecerem subutilizados, A-01 já roteia para eles via Haiku — eliminá-los exige verificar `_FALLBACK_POR_FAMILIA` e o ROTAS do `a01_junior.py`. Inventariar uso real (P2-7) **antes** de deletar.
- **Não migrar para microsserviços** — monolítica modular cabe no volume atual; complexidade ops não se justifica.
- **Não reescrever XGBoost scorer heurístico** sem dataset rotulado de fraudes reais — vai trocar um heurístico por outro.
- **Não adotar OpenTelemetry completo agora** — Sentry + 4 métricas resolvem o problema imediato.

---

## 5. Arquivos críticos identificados

- `api/main.py` — entrypoint FastAPI, **P0-7** (silent `try/except` linhas 71-77), P2-3 (CORS hardcoded)
- `api/middleware/rate_limit.py` — P0-3
- `api/services/auditoria_nfae.py` — P0-2 (estado `tasks_status`, `resultados_store`)
- `api/routes/auditoria.py` — P0-1 (validação upload), P0-6 (hash PDF)
- `api/auth/security.py` — P1-2 (refresh revocation), P1-3 (passlib)
- `horizon_blue_one/core/privacy.py` — P0-5 (log @Delta)
- `horizon_blue_one/core/model_adapter.py` — P2-5 (versionamento prompt)
- `horizon_blue_one/core/token_router.py` — P1-8 (persistir stats)
- `horizon_blue_one/agents/a01_junior.py` — **P1-7** (`_ledger` in-memory)
- `horizon_blue_one/agents/a00_ceo.py` — referência de hardening (não precisa mexer)
- `horizon_blue_one/orgaudi/regra_especial_1.py` — P0-4
- `horizon_blue_one/orgaudi/resumo_fiscal.py` — P0-4, P1-1
- `horizon_blue_one/orgaudi/anomalias.py` — P0-4
- `horizon_blue_one/agents/a07_auditoria_assurance.py` — P1-5
- `horizon_blue_one/agents/a08_auditor_nfa.py` — P1-5
- `horizon_blue_one/agents/detectores_forenses.py` — P1-5
- `nfa_extractor/infrastructure/ai_client.py` — circuit breaker (P0-2 relacionado)
- `frontend/frontend/vite.config.js` — P2-4
- `requirements.txt` — P1-3 (passlib/bcrypt)
- `alembic/versions/001_initial.py` — P1-4 (PostgreSQL)

---

*OrgAudi Sovereign Shield — ORGATEC v8.0.0 — Relatório de Mapeamento e Aprimoramento*
