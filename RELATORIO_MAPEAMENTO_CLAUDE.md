# Relatório de Mapeamento, Limpeza e Melhorias — AudiOrg-1.1

**Autor:** Análise automatizada Claude (Anthropic)
**Data:** 2026-05-14
**Branch analisada:** `main` (HEAD `5d98209`)
**Status do CI:** ✅ Verde (run #80 — todos os 5 jobs passando)

---

## 1. Sumário Executivo

O repositório `AudiOrg-1.1` (OrgAudi Sovereign v8.0) é uma plataforma de auditoria fiscal de NFA-e composta por backend FastAPI, frontend React 19, pipeline de auditoria (HORIZON-BLUE ONE), extrator de PDF e motor de geração de PDF. Após resolver 4 problemas críticos de CI (pandas, datetime.UTC, pytest-asyncio e Alembic heads), este documento mapeia a estrutura atual, identifica arquivos obsoletos e propõe melhorias de qualidade.

**Pontos fortes:** boa cobertura de testes (45%+), arquitetura modular clara em 4 módulos, migrações Alembic linearizadas, protocolo de privacidade @Delta implementado.

**Principais problemas detectados:**
- ~33 agentes arquivados em `horizon_blue_one/agents/_archived/` ainda versionados.
- ~14 pastas de simulação e outputs JSON/MD em `out/` versionados (deveriam estar em `.gitignore`).
- `pdf_engine/_legacy/` contém 3 versões antigas (`orgaudi_v240`, `orgaudi_v250`, `orgaudi_v4`) ainda no repositório.
- Múltiplos relatórios `.md` redundantes na raiz (ver seção 4).
- `.gitignore` não cobre `out/` nem `reports_nfa/` (artefatos de runtime).

---

## 2. Mapa dos Módulos Ativos

### 2.1 `api/` — Backend FastAPI 8.0
- **`api/main.py`** — Entrypoint. Lifespan, CORS, RateLimit, carrega 6 routers fixos + 2 opcionais (`metrics`, `nfa_ai_parser`).
- **`api/auth/`** — JWT (argon2id + bcrypt legacy), revogação de refresh tokens via jti.
- **`api/middleware/rate_limit.py`** — 60 req/60s por IP, backend Redis com fallback in-memory.
- **`api/routes/`** — `auth`, `auditoria`, `clientes`, `agente`, `chat`, `batch`, `metrics`, `nfa_ai_parser`.
- **`api/services/`** — `auditoria_nfae` (orquestrador principal), `auditoria_bigfour` (forense), `auditoria_tasks` (assíncrono).
- **Estado:** Coeso e bem testado. Pequena dívida: arquivo `auditoria.py` em services existe como shim (compatibilidade).

### 2.2 `horizon_blue_one/` — Pipeline de Auditoria
- **`agents/`** — Apenas 4 agentes ativos: `a07_auditoria_assurance`, `a08_auditor_nfa`, `base_agent`, `detectores_forenses`.
- **`agents/_archived/`** — 33 arquivos arquivados (a00–a27 + a_chat, a_ingest, a_narrative, a_ranking, a_resolver, a_token). **Candidatos a remoção.**
- **`core/`** — `config.py`, `model_adapter.py` (retry tenacity), `ledger.py`, `privacy.py` (@Delta), `token_router.py`.
- **`ml/`** — `xgboost_scorer.py` (8 features → score 0–100, modo heurístico se .pkl ausente).
- **`orgaudi/`** — `regra_especial_1.py` (RE-1), `resumo_fiscal.py` (F1-F6 FUNRURAL 2026).

### 2.3 `nfa_extractor/` — Extração + Infra
- **`domain/`** — `extractor.py`, `schemas.py`, `constants.py`, `nfa_parser_ai.py`.
- **`infrastructure/`** — `database_v2.py` (SQLAlchemy 2.0), `logging_config.py` (structlog), `ai_client.py`, `audit_task_repo.py`, integração Supabase.
- **`application/`** — `agents_engine.py`, `analytics_engine.py`, `audit_service.py`, `sovereign_engine.py`.
- **`utils/validators.py`** — CPF, CNPJ, chave NF-e.

### 2.4 `pdf_engine/` — Geração de PDF
- **`orgaudi/`** — Motor atual em uso pelo `auditoria_nfae`.
- **`_legacy/orgaudi_v240`**, **`_legacy/orgaudi_v250`**, **`_legacy/orgaudi_v4`** — versões antigas. **Candidatos a remoção.**
- **`_legacy/ir_report.py`**, **`_legacy/pdf_report.py`** — relatórios legados.
- **`excel_export.py`** — export Excel (openpyxl).

### 2.5 `alembic/versions/` — Migrações
Cadeia linear correta: `001_initial → 002_audit_results_and_pdf_hash → 003_ledger_entries → 004_claude_stats`.

### 2.6 `tests/` — Suíte pytest
255 testes coletados, 253 passam após fix do pytest-asyncio. Cobertura: **45.66%** (limite mínimo: 30%).

### 2.7 `frontend/frontend/` — React 19
LoginPage, Dashboard, AuditoriaModule, MatrixBackground, services/api.js.

### 2.8 `k8s/` — Helm charts (deploy)

### 2.9 `scripts/` — Utilitários CLI

---

## 3. Erros Corrigidos Nesta Sessão

| # | Arquivo/Componente | Problema | Correção | Commit |
|---|---|---|---|---|
| 1 | `requirements.txt` | `pandas>=3.0.2` requer Python ≥3.11; CI testava 3.10 | `pandas>=2.2.0` | `233c06b` |
| 2 | `api/auth/security.py` | `from datetime import UTC` falha em Python 3.10 | Trocou para `timezone.utc` | `bdf5d35` |
| 3 | `.github/workflows/ci.yml` | `pytest-asyncio` não instalado, testes async falhavam | Adicionado ao install | `5d98209` |
| 4 | `alembic/versions/` | "Multiple head revisions" em runs antigos | Já resolvido em `59156e1` | — |

---

## 4. Arquivos Recomendados para Remoção

### 4.1 Agentes arquivados (33 arquivos)
`horizon_blue_one/agents/_archived/` — 27 agentes numerados (a00–a27, exceto a07/a08 ativos) + 6 prefixados `a_*`. Substituídos pelo pipeline atual.

### 4.2 Outputs versionados (toda a pasta `out/`)
- 14 pastas `simulacao_*`
- `ledger.jsonl` (já substituído pela tabela `ledger_entries` na migração 003)
- 8 arquivos `horizon_full_*.{json,md}`
- 4 arquivos `analise_*` e `teste_*.json`

### 4.3 Outputs em `reports_nfa/`
- `llm_alto_risco_*.json` (3)
- `lote_completo_*.json` (2)
- `RELATORIO_TOKENS_*.md` (2)
- `EMAIL_warmove6_2026-05-10.txt`
- pasta `laudos_pdf/`

### 4.4 PDF Engine legado (`pdf_engine/_legacy/`)
- `orgaudi_v240/` (motor 2.4 — substituído por `pdf_engine/orgaudi/`)
- `orgaudi_v250/` (motor 2.5)
- `orgaudi_v4/` (adaptador legado)
- `ir_report.py`, `pdf_report.py`

### 4.5 Documentação redundante na raiz
Os seguintes `.md` na raiz parecem duplicar/superpor:
- `ATUALIZADO_SCORE_9.0.md`
- `DECISAO_AGENTES_LIMPEZA.md`
- `RELATORIO_AGENTES_E_TECNOLOGIAS.md`
- `RELATORIO_FINAL_CONSOLIDADO.md`
- `RELATORIO_MAPEAMENTO.md`
- `SCORE_SAUDE_PROJETO.md`
- `SUMARIO_EXECUTIVO.txt`

Recomendação: consolidar em `docs/` (já existe `docs/MAPEAMENTO_E_APRIMORAMENTO_v8.md`).

### 4.6 `pdf_engine/MAPEAMENTO_UNIFICACAO.md`
Documento histórico de migração — mover para `docs/historico/`.

---

## 5. Melhorias Recomendadas

### 5.1 Curto prazo (alta prioridade)

1. **Adicionar ao `.gitignore`:**
   ```
      out/
         reports_nfa/*.json
            reports_nfa/*.md
               reports_nfa/*.txt
                  reports_nfa/laudos_pdf/
                     ```
                     2. **Adicionar `pytest-asyncio` ao `requirements.txt`** (atualmente só está no workflow).
                     3. **Pinar versões críticas** em `requirements.txt` (atualmente quase tudo é `>=`, o que causa drift e quebras como a do pandas 3.x).
                     4. **Atualizar README:** remove menções a `finance.py` (removido) e ARankingAgent (arquivado).
                     5. **Criar `CHANGELOG.md`** consolidado a partir dos vários `.md` da raiz.

                     ### 5.2 Médio prazo

                     6. **Coverage mínimo:** subir gradualmente de 30% → 50% → 70%.
                     7. **Type hints estritos:** adicionar `mypy --strict` em CI separado.
                     8. **Linting:** adicionar `ruff check` no workflow CI (já há `.ruff_cache/` no gitignore, sugerindo intenção prévia).
                     9. **Security headers:** adicionar middleware com `X-Content-Type-Options`, `Strict-Transport-Security`, `Referrer-Policy`.
                     10. **Observability:** completar integração Sentry/Prometheus (PR #49 implementou parcialmente).
                     11. **Frontend tests:** não há testes Vitest/Jest no `frontend/frontend/`.

                     ### 5.3 Longo prazo

                     12. **Mono-repo cleanup:** considerar mover `frontend/frontend/` para `frontend/` (camada dupla redundante).
                     13. **CI matrix:** adicionar Python 3.13 quando dependências estabilizarem.
                     14. **Docker:** o `docker-compose.yml` existe — incluir healthcheck + Dockerfile dedicado para a API.
                     15. **Dependabot:** ativo (visto pelos PRs `chore(deps)`), mas múltiplas atualizações estão falhando — agrupar updates por categoria (`groups:` no `dependabot.yml`).
                     16. **Documentação de API:** publicar OpenAPI/Swagger em `/docs` (FastAPI já gera automaticamente; basta documentar acesso).

                     ---

                     ## 6. Riscos Conhecidos

                     | Risco | Severidade | Mitigação proposta |
                     |---|---|---|
                     | Drift de versões `>=` em `requirements.txt` | Alta | Pinar versões + Dependabot grouped |
                     | `out/` cresce sem limite em produção | Média | `.gitignore` + rotação por data |
                     | Falta de testes frontend | Média | Adicionar Vitest + React Testing Library |
                     | `JWT_SECRET_KEY` fallback em dev | Baixa | Já tratado; verificar `APP_ENV=production` em deploy |
                     | Coverage limite baixo (30%) | Média | Subir gradualmente |

                     ---

                     ## 7. Conclusão

                     O projeto está em estado funcional e o CI agora está estável. As principais oportunidades de melhoria estão em:
                     1. **Limpeza** de aproximadamente 70+ arquivos obsoletos (agentes arquivados, outputs, legacy PDF engines).
                     2. **Endurecimento** das dependências (versões pinadas).
                     3. **Consolidação** da documentação dispersa em raiz.

                     Após executar a limpeza recomendada, o repositório ficará significativamente mais enxuto e mais fácil de navegar, sem perder nenhuma funcionalidade — todos os arquivos listados para remoção são confirmadamente não-referenciados pelo código ativo.

                     ---

                     *Fim do relatório.*
                     
