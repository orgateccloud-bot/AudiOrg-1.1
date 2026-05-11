# Mapeamento Completo & Relatório de Aprimoramento — OrgAudi Sovereign v8.0.0

> **Data:** 2026-05-11
> **Versão analisada:** v8.0.0
> **`main` (commit `790842f`):** ainda contém os 28 agentes legados A-00..A-27.
> **Branch `feat/orchestrator-mix-80-15-5` ([PR #13](https://github.com/orgateccloud-bot/AudiOrg-1.1/pull/13)):** consolida 28 → **7 agentes S1..S7** + nova camada `core/` (orchestrator, precalc, ledger, limiares, prompt_compactor) + mix 80/15/5 + PF-Gate determinístico.

Este documento mapeia a arquitetura **atual de `main`** e a **futura** introduzida pelo PR #13, lista o quê cada agente legado virou em S1..S7, e propõe recomendações priorizadas considerando ambos os estados. Os itens marcados ✅ foram parcial ou totalmente endereçados pelo PR #13.

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
│ ┌──────────┐   │ │   infrastructure/ │ │ orgaudi_v250/    │
│ │ main:    │   │ │   application/    │ │ orgaudi_v4/      │
│ │ 28 A-XX  │   │ │   utils/          │ │ pdf_report.py    │
│ ├──────────┤   │ │                   │ │ ir_report.py     │
│ │ PR #13:  │   │ │                   │ │ excel_export.py  │
│ │ S1..S7   │   │ │                   │ │ (3 versões!)     │
│ │ +_legacy │   │ │                   │ │                  │
│ │ +orch/   │   │ │                   │ │                  │
│ │  precalc/│   │ │                   │ │                  │
│ │  ledger/ │   │ │                   │ │                  │
│ │  limiares│   │ │                   │ │                  │
│ │ +nfa_    │   │ │                   │ │                  │
│ │  bridge  │   │ │                   │ │                  │
│ └──────────┘   │ │                   │ │                  │
└────────────────┘ └───────────────────┘ └──────────────────┘
                           │
                ┌──────────┼──────────┐
                │          │          │
        SQLAlchemy 2.0  Anthropic   Supabase
        + SQLite        Claude API  (opcional)
        (Alembic)       (Sonnet/    finance/*
                         Haiku/Opus)
```

**Fluxo de auditoria NFA-e — versão `main`:**
```
PDF NFA-e → pdfplumber → RE-1 → XGBoost → F1-F6 → A-07 → A-08 → A-00 → pdf_engine
```

**Fluxo de auditoria NFA-e — versão PR #13 (orchestrator):**
```
PDF NFA-e → pdfplumber
  → precalcular() roda 1× e produz cache __precalc__
       (PII, documentos, detectores, xgboost, cfop, lcdpr, itr, grafo, caixa, notas_re1)
  → PF-Gate determinístico (limiares.py):
       prob < 0.40 → ARQUIVA (0 chamadas LLM, parecer determinístico)
       prob < 0.65 → REDUZIDO (S3 + S5 + S7)
       prob < 0.85 → AMPLO    (S1 + S2 + S3 + S5 + S7)
       prob ≥ 0.85 → COMPLETO (S1..S7)
  → Orchestrator (asyncio) executa agentes selecionados em sequência
       EventBus publica ESCALADO/APROVADO/REJEITADO/ERRO/CONCLUIDO
       resultados_agentes acumula no payload entre passos
  → S7 @CEO sempre por último, agrega tudo, gera MD&A
  → pdf_engine/orgaudi_v* → PDF laudo
```

---

## 2. Agentes — Mapa Antigo (`main`) e Novo (PR #13)

### 2.1. Estado em `main` — 28 agentes A-00..A-27 + a_token

Camada de orquestração unificada por três agentes-pivô:

- **A-01 @Junior** — Manager Router via Haiku, com `AGENTES_VALIDOS` frozenset anti-injection
- **A-Token @Token** — Roteador econômico de modelo (Haiku/Sonnet/Opus)
- **A-00 @CEO** — Governança final com `ORIGEM_SCORE_CONFIAVEL` anti-prompt-injection

### 2.2. Estado no PR #13 — 7 agentes S1..S7

| ID  | Nome         | Substitui (agentes legados)                                       | Modelo                                              |
|-----|--------------|-------------------------------------------------------------------|-----------------------------------------------------|
| **S1** | @Sentinel  | A-02 (Protetor) + A-03 (ZeroTrust) + A-09 (Auditor-TI) + A-16 (LGPD) | **Haiku 4.5** (verde determinístico sem LLM se PII=0 + pendências=0 + IE válida) |
| **S2** | @Forense   | A-04 (Vigilante) + A-07 (Assurance) + A-23 (Anomalias) + A-27 (Epsilon Grafo) | **Sonnet 4.6** → **Opus 4.7** se score≥85 ou ≥3 tipologias |
| **S3** | @Fiscal    | A-11 (Tributário) + A-21 (ICMS) + A-22 (ITR) + A-24 (CFOP) + A-25 (LCDPR) | Sonnet 4.6                                          |
| **S4** | @Contabil  | A-10 (Patrimônio) + A-17 (Caixa) + A-19 (Contabilista) + A-26 (Biológicos/CPC 29) | Sonnet 4.6                                          |
| **S5** | @AuditorNFA| A-06 (Extrator) + A-08 (AuditorNFA)                                | Sonnet 4.6                                          |
| **S6** | @RH        | A-20 (eSocial) + FGTS + INSS                                       | Sonnet 4.6                                          |
| **S7** | @CEO       | A-00 (CEO) + A-14 (Risco) + A-15 (Jurídico) + A-18 (CSuite/MD&A)   | **Sonnet 4.6** → **Opus 4.7** se score≥85 ou valor>R$1M ou ≥3 tipologias |

Agentes do `main` que não aparecem no mapa S1..S7 (e o porquê):
- **A-01 (Junior router)** — desnecessário; pipeline agora é sequencial determinístico
- **A-05 (Engenheiro-ERP)** — funcionalidade migrou para `nfa_bridge/`
- **A-12 (Descobridor-Deducoes)** — funcionalidade absorvida em S3 @Fiscal
- **A-13 (Monitor-Conformidade)** — funcionalidade absorvida em S1 @Sentinel + S7 @CEO
- **a_token** — virou infraestrutura (`call_otimizado()` chamado direto pelos agentes)

Os 28 agentes legados permanecem em `horizon_blue_one/agents/_legacy/` para rollback e regressão. O `orchestrator.py` registra alias `A-00` → `s7_ceo` para compat.

### 2.3. Mix de modelos 80/15/5 (rev 2026-05-09)

| Modelo  | Distribuição | Aplicação                                                  |
|---------|-------------|------------------------------------------------------------|
| Haiku 4.5 | **80%**   | S1 (Sentinel) + 22 agentes operacionais legacy             |
| Sonnet 4.6 | **15%**  | S2/S3/S4/S5/S6/S7 (default), A-07/A-15/A-23/A-27 legacy    |
| Opus 4.7 | **5%**    | S2/S7 em upgrade crítico (score≥85, ≥3 tipologias, valor>R$1M) |

Escalada **Sonnet→Opus apenas** — Haiku permanece Haiku no crítico. Evita explosão de custo +400% → +28% no pior caso (medido em scripts/simulacao_mix_modelos.py).

### 2.4. PF-Gate determinístico (`core/limiares.py`)

Filtra produtores **antes** de chamar qualquer agente LLM. Limiares:

| Limiar (prob_autuacao) | Comportamento                                          |
|-----------------------|---------------------------------------------------------|
| `< 0.40` (ARQUIVA)    | Parecer determinístico, 0 chamadas LLM                  |
| `< 0.65` (REDUZIDO)   | Só S3 + S5 + S7 (fiscal/NFA/CEO)                        |
| `< 0.85` (AMPLO)      | S1 + S2 + S3 + S5 + S7 (sem S4 contábil / S6 RH)        |
| `≥ 0.85`              | Pipeline completo S1..S7                                |

Calibração só com aprovação CRC-GO (documentado em `limiares.py`).

### 2.5. Pré-cálculo determinístico (`core/precalc.py` — 14.8 KB)

Centraliza todo cálculo determinístico em UM passe paralelo antes que qualquer agente LLM rode. Resolve as falhas F1/F2/F13/F14:

- F1: detectores forenses rodavam 2× (A-07 + A-23) → agora 1× em precalc
- F2: `extrair_features_completas` chamava detectores 5× por audit → agora cache
- F13: `detectar_devolucao_posterior` corrigido (sem multiplicar por 1.1)
- F14: RE-1 aplicada **antes** de @Delta para evitar dupla anonimização

Cache `__precalc__` contém: `notas_re1`, `pii`, `documentos`, `detectores`, `xgboost`, `cfop`, `lcdpr`, `itr`, `grafo`, `caixa`.

### 2.6. Detectores forenses (inalterados)

`CARROSSEL_FISCAL`, `SMURFING_RURAL`, `FORNECEDOR_FANTASMA`, `DEVOLUCAO_POSTERIOR`, `ANOMALIA_TEMPORAL`. Todos determinísticos, sem LLM. Agora chamados uma vez por `precalc.precalcular()` e consumidos via `get_precalc()` por S2.

### 2.7. Catálogo AN-01..AN-18 (inalterado)

Smurfing, carrossel, nota fria, sub/superfaturamento, CFOP indevido, trânsito não realizado, transferência intrafamiliar, IE inativa, período suspeito, volume incompatível, caixa dois, concentração atípica, devolução sistemática, Funrural subdeclarado, ITR divergente, sobreposição de períodos, ausência de GTA.

---

## 3. Tecnologias

| Camada            | Stack                                                                    | Versão        |
|-------------------|--------------------------------------------------------------------------|---------------|
| Frontend          | React + Vite + Tailwind + React Router + Axios + Framer Motion + Lucide  | 19.2 / 8.0 / 4.2 / 7.14 |
| API               | FastAPI + Uvicorn + Pydantic v2 + python-multipart                       | 0.104+ / 0.24+ |
| Auth              | python-jose (JWT HS256) + passlib + bcrypt                                | 3.3+ / 1.7.4 / <4.0 |
| DB                | SQLAlchemy 2.0 + Alembic + SQLite (dev) / PostgreSQL via psycopg2 + Supabase | 2.0+ / 1.x / 2.0+ |
| LLM               | anthropic SDK (Claude) + google-genai (Gemini opcional)                  | 0.49+ / 0.2+ |
| Orquestração      | `core/orchestrator.py` (asyncio + EventBus) — PR #13                     | custom (17.6KB) |
| Pré-cálculo       | `core/precalc.py` — cache determinístico paralelo — PR #13               | custom (14.8KB) |
| Ledger            | `core/ledger.py` — JSONL append-only em `out/ledger.jsonl` — PR #13      | custom (2.3KB)  |
| Limiares          | `core/limiares.py` — constantes centralizadas — PR #13                   | custom (3KB)    |
| Roteamento modelo | `core/token_router.py` — mix 80/15/5 calibrado por agente                 | custom (18.3KB) |
| Prompt compaction | `core/prompt_compactor.py` — `kv()` para tokens reduzidos — PR #13       | custom (2.8KB)  |
| ML                | xgboost + scikit-learn + pandas + numpy                                  | 2.1+ / 1.3+ / 2.0+ |
| PDF               | pdfplumber + PyMuPDF + reportlab + openpyxl + Pillow + matplotlib        | 0.10+ / 1.24+ / 4.0+ |
| Logging           | structlog + tenacity + defusedxml                                        | 24.0+ / 9.0+ |
| Privacidade       | Protocolo @Delta (anonimiza CPF/CNPJ/nomes pré-LLM)                      | custom (1KB)  |
| Bridge NFA        | `horizon_blue_one/nfa_bridge/` — PR #13                                  | novo módulo   |
| CI/CD             | GitHub Actions: pytest (3.10/3.11/3.12) + frontend build + TruffleHog    | —             |
| Tests             | pytest + `horizon_blue_one/tests/smoke_tests` (PR #13) — cobertura ainda baixa em regras fiscais |  |

**Achados de risco em `main`:**

1. **`api/main.py` linhas 71-77** — silent failure: `try/except: pass` engole erros de import de `metrics`, `finance`, `nfa_ai_parser`. Endpoints inteiros desaparecem sem log.
2. **`api/routes/auditoria.py` linha 48-61** — endpoint `/upload/{client_id}` recebe `List[UploadFile]` sem limite de tamanho/MIME/magic-bytes.
3. **`api/main.py` linhas 57-60** — origens CORS hardcoded para `localhost:5173-5175`.
4. **`api/services/auditoria_nfae.py`** — `tasks_status`, `resultados_store` mantidos em dicts in-memory.
5. **`horizon_blue_one/agents/a01_junior.py`** — `_ledger: list = []` na classe; perdido em restart. ✅ **Resolvido parcialmente no PR #13** por `core/ledger.py` (JSONL em `out/ledger.jsonl`). Produção ainda precisa migrar para Postgres.

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

### P0 — Bloqueia produção segura

| #  | Item                                                              | Status                                                                                       |
|----|-------------------------------------------------------------------|----------------------------------------------------------------------------------------------|
| P0-1 | Validar tamanho/MIME/magic-bytes do upload PDF                    | Endpoint público sem limite = DoS trivial + vetor de PDF malicioso. 2h.                       |
| P0-2 | Persistir `tasks_status` e `resultados_store` em Redis/Postgres   | Restart no meio de uma task = laudo perdido. Risco LGPD por dado órfão. **Não tocado pelo PR #13.** |
| P0-3 | Mover rate limit para Redis                                       | In-memory é furado por restart e multi-instância. **Não tocado pelo PR #13.**                 |
| P0-4 | Cobertura de testes RE-1, F1-F6, AN-01..AN-18                     | ✅ **Parcialmente resolvido**: PR #13 adiciona `horizon_blue_one/tests/smoke_*` e smoke LLM-real para 6 produtores de ALTO risco. Ainda P0 porque cobertura geral continua baixa. |
| P0-5 | Log append-only de des-anonimização @Delta                        | LGPD Art. 37: quem viu qual CPF/CNPJ real, quando, com qual prompt. **Não tocado.**           |
| P0-6 | Hash SHA-256 do PDF emitido salvo no banco                        | PDF é evidência jurídica. Sem checksum, não há prova de integridade. **Não tocado.**          |
| P0-7 | Substituir `try/except: pass` em `api/main.py:71-77` por log     | Silent failure faz endpoints inteiros desaparecerem sem alerta. 15 min de fix. **Não tocado.** |

### P1 — Próximo ciclo (4-8 semanas)

| #  | Item                                                              | Status                                                                                       |
|----|-------------------------------------------------------------------|----------------------------------------------------------------------------------------------|
| P1-1 | Externalizar alíquotas FUNRURAL para YAML versionado              | Alíquotas mudam por ato normativo. Hoje cada mudança vira deploy. **Não tocado.**             |
| P1-2 | Revogação de refresh token (`jti` + blacklist Redis)              | Token vazado de auditor sem kill switch.                                                      |
| P1-3 | Migrar passlib+bcrypt<4.0 → argon2-cffi ou pwdlib                 | passlib é abandonware.                                                                        |
| P1-4 | SQLite → PostgreSQL em produção                                   | Trava acima de ~10 escritas/s; sem PITR; sem RLS.                                             |
| P1-5 | Fixtures determinísticas para os 5 detectores de A-07              | ✅ **Parcialmente resolvido** pelo PR #13 (smoke tests determinísticos).                       |
| P1-6 | Sentry + 4 métricas Prometheus (laudos/h, p95, erro S-agents, $token/dia) | `/tokens` e `/metrics/ai` existem mas não exportam Prometheus.                            |
| P1-7 | Persistir ledger do A-01 fora de `_ledger: list = []` in-memory    | ✅ **Resolvido parcialmente**: `core/ledger.py` grava JSONL em `out/ledger.jsonl`. Falta migrar JSONL → Postgres em produção (arquivo único cresce indefinidamente e não suporta multi-instância). |
| P1-8 | Persistir `get_stats()` do `token_router` em Postgres              | Stats de custo Claude resetam no restart, impossibilitando rastreio mensal.                   |
| **P1-9** | **(novo) Garantir isolamento do cache `__precalc__` entre requisições** | O cache é criado por payload, mas precisa de teste explícito que valide que dados de um produtor não vazam para outro (LGPD). |
| **P1-10** | **(novo) Migrar `out/ledger.jsonl` para tabela Postgres**     | Arquivo único cresce sem rotação e impede multi-instância. Promover P1-7 para finalização total. |

### P2 — Próximo trimestre

| #  | Item                                                              | Status                                                                                       |
|----|-------------------------------------------------------------------|----------------------------------------------------------------------------------------------|
| P2-1 | ruff + black + pre-commit                                          | Acelera todo o resto. 1 dia.                                                                  |
| P2-2 | Dockerfile + docker-compose                                        | Onboarding e ambiente reproduzível.                                                            |
| P2-3 | CORS via env var (hoje hardcoded localhost:5173-5175 em `main.py`) | Bloqueia deploy em staging/prod.                                                              |
| P2-4 | Frontend backend URL via `VITE_API_URL` (hoje `:8082` hardcoded)   | Mesmo motivo.                                                                                  |
| P2-5 | Versionamento de prompts LLM (`prompts/` com hash em cada chamada) | Mudança silenciosa de prompt pode mudar veredito.                                              |
| P2-6 | tsconfig.json no frontend                                          | Já usa `@types/react` — falta config explícita.                                               |
| ~~P2-7~~ | ~~Documentar uso real dos 30 agentes~~                          | ✅ **Resolvido pelo PR #13**: consolidação 28 → 7 com `_legacy/` preservado.                  |
| **P2-8** | **(novo) Suporte a override por cliente nos `limiares.py`**    | Produtores grandes podem precisar de thresholds diferentes (ex.: SCORE_ALTO em vez de 65 → 70 para clientes com histórico limpo). Hoje os limiares são globais. |
| **P2-9** | **(novo) Auditoria do PF-Gate**                                 | PF-Gate filtra produtores antes de S1..S7 — é eficiente, mas a decisão de "ARQUIVAR" sem LLM precisa de trilha auditável CRC-GO (que produtor foi arquivado e por quê). |

### P3 — Adiar conscientemente

| #  | Item                                                              | Por quê adiar                                                                                 |
|----|-------------------------------------------------------------------|-----------------------------------------------------------------------------------------------|
| P3-1 | Consolidar pdf_engine v240/v250/v4                                 | Só após snapshot tests (P3-2).                                                                |
| P3-2 | Snapshot tests de PDF gerado                                       | Pesado; só vale quando atacar P3-1.                                                            |
| P3-3 | Upgrade LangGraph 0.1 → 0.3                                        | Breaking changes; menos crítico após PR #13 reduzir dependência via orchestrator próprio.    |
| P3-4 | Integração CEPEA real (AN-04/AN-05)                                | Depende de contrato CEPEA-USP. Decisão de produto.                                            |
| P3-5 | Testes frontend (vitest)                                           | Adicionar quando o frontend mudar substancialmente.                                            |
| P3-6 | OpenTelemetry completo                                             | Sentry + 4 métricas resolvem 80% com 10% do esforço.                                          |
| **P3-7** | **(novo) Deletar `agents/_legacy/` após 2 ciclos de produção** | Hoje preservado para rollback. Quando S1..S7 estiver estável por 2+ meses, remover.            |

### Quick-wins (<1 dia cada, ROI alto)

1. **Fix do silent `try/except: pass` em `api/main.py:71-77`** (P0-7) — 15 minutos.
2. **Validação upload PDF** (P0-1) — 2h, fecha DoS.
3. **Hash SHA-256 do PDF emitido** (P0-6) — 2h, fecha gap de integridade jurídica.
4. **ruff + pre-commit** (P2-1) — meio dia, destrava todo o resto.
5. **CORS via env + backend URL via env** (P2-3, P2-4) — 1h.
6. **YAML de alíquotas Funrural** (P1-1) — meio dia.

### Anti-recomendações (NÃO fazer agora)

- **Não consolidar `pdf_engine/v240/v250/v4`** sem snapshot tests — risco de quebrar laudos.
- **Não atualizar LangGraph 0.1 → 0.3** antes de S-agents com cobertura >70%.
- ~~**Não reduzir o número de agentes**~~ ✅ **Já feito com cuidado pelo PR #13** (`_legacy/` preservado, alias `A-00` → `s7_ceo`, smoke tests dos 28 + 7).
- **Não migrar para microsserviços** — monolítica modular cabe no volume atual.
- **Não reescrever XGBoost scorer heurístico** sem dataset rotulado de fraudes reais.
- **Não adotar OpenTelemetry completo agora** — Sentry + 4 métricas resolvem o problema imediato.
- **Não deletar `_legacy/` agora** — espere 2 ciclos de produção com S1..S7 estável antes.

---

## 5. Arquivos críticos identificados

### Em `main` (commit `790842f`):

- `api/main.py` — **P0-7** (silent `try/except` linhas 71-77), P2-3 (CORS hardcoded)
- `api/middleware/rate_limit.py` — P0-3
- `api/services/auditoria_nfae.py` — P0-2 (`tasks_status`, `resultados_store`)
- `api/routes/auditoria.py` — P0-1, P0-6
- `api/auth/security.py` — P1-2, P1-3
- `horizon_blue_one/core/privacy.py` — P0-5
- `horizon_blue_one/core/model_adapter.py` — P2-5
- `horizon_blue_one/orgaudi/regra_especial_1.py` — P0-4
- `horizon_blue_one/orgaudi/resumo_fiscal.py` — P0-4, P1-1
- `horizon_blue_one/orgaudi/anomalias.py` — P0-4
- `nfa_extractor/infrastructure/ai_client.py` — circuit breaker
- `frontend/frontend/vite.config.js` — P2-4
- `requirements.txt` — P1-3
- `alembic/versions/001_initial.py` — P1-4

### No PR #13 (`feat/orchestrator-mix-80-15-5`):

- `horizon_blue_one/core/orchestrator.py` — pipeline + EventBus + registry S1-S7 + alias `A-00` → `s7_ceo`
- `horizon_blue_one/core/precalc.py` — cache `__precalc__` (revisar P1-9: isolamento entre requisições)
- `horizon_blue_one/core/ledger.py` — P1-10 (JSONL → Postgres)
- `horizon_blue_one/core/limiares.py` — P2-8 (override por cliente)
- `horizon_blue_one/agents/s1_sentinel.py` ... `s7_ceo.py` — 7 agentes consolidados
- `horizon_blue_one/agents/_legacy/` — 28 agentes preservados (P3-7: deletar após 2 ciclos)
- `horizon_blue_one/nfa_bridge/` — novo módulo de bridge NFA
- `horizon_blue_one/tests/` — smoke tests (parcialmente resolvem P0-4 e P1-5)

---

## 6. Evolução desde a análise inicial

O PR #13 já endereçou **5 das 21 recomendações** originais, total ou parcialmente:

| Item       | Status                                                                                       |
|------------|----------------------------------------------------------------------------------------------|
| **P0-4**   | ✅ Parcial — smoke tests determinísticos + LLM-real (6 produtores ALTO risco)                |
| **P1-5**   | ✅ Parcial — fixtures dos detectores via smoke tests                                          |
| **P1-7**   | ✅ Parcial — ledger JSONL em `out/ledger.jsonl` (precisa virar Postgres em prod → P1-10)     |
| **P2-7**   | ✅ Total — 28 agentes consolidados em 7 com `_legacy/` preservado                              |
| **Anti-rec "não reduzir agentes"** | ✅ Removida — consolidação feita com `_legacy/` para rollback         |

**Novos pontos surgidos com a arquitetura S1..S7:**

- **P1-9 (novo):** garantir isolamento do cache `__precalc__` entre requisições (teste explícito de não-vazamento entre produtores)
- **P1-10 (novo):** migrar `out/ledger.jsonl` para tabela Postgres (multi-instância + rotação)
- **P2-8 (novo):** override de `limiares.py` por cliente (clientes grandes com histórico limpo)
- **P2-9 (novo):** auditoria CRC-GO da decisão "ARQUIVAR" do PF-Gate (sem LLM, ainda assim precisa rastro)
- **P3-7 (novo):** deletar `_legacy/` após 2 ciclos de produção

---

*OrgAudi Sovereign Shield — ORGATEC v8.0.0 — Relatório de Mapeamento e Aprimoramento*
*Atualizado em 2026-05-11 com a arquitetura S1..S7 do PR #13.*
