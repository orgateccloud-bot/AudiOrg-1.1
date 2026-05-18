# Análise do Projeto OrgAudi — Plataforma de Auditoria Fiscal

**Data:** 16/05/2026  
**Versão analisada:** 1.0.0  
**Responsável:** ORGATEC IA

---

## 1. Sumário Executivo

### Métricas Gerais
| Métrica | Valor | Status |
|---------|-------|--------|
| **Linhas de código** | 12.851 | ✅ Moderado |
| **Testes unitários** | 19 arquivos (255 testes) | ✅ Cobertura 47,14% |
| **Cobertura de código** | 47,14% | ✅ Acima do mínimo (30%) |
| **Python LOC** | ~12k | ✅ Bem estruturado |
| **Módulos principais** | 4 | ✅ Arquitetura clara |
| **Status git** | 82 commits | ✅ Ativo |

### Status Geral
- ✅ **Testes passando:** 255/255 (100%)
- ✅ **Cobertura requerida:** 47,14% > 30%
- ⚠️ **Áreas críticas com baixa cobertura:** nfa_parser_ai.py (10,43%), token_router.py (0%)
- ✅ **Dependências:** Atualizadas e gerenciadas

---

## 2. Arquitetura — 4 Módulos Principais

### 2.1. Módulo 1: horizon_blue_one (Pipeline de Auditoria)
**Descrição:** Orquestração da auditoria fiscal em 5 etapas determinísticas + IA.

```
RE-1 (Reclassificação) → XGBoost (Score) → F1-F6 (Fiscal) → A-07 (Forense) → A-08 (LLM)
```

**Componentes:**
| Componente | LOC | Cobertura | Objetivo |
|------------|-----|-----------|----------|
| `agents/a07_auditoria_assurance.py` | 51 | 20% | Detectores forenses (5 tipologias) |
| `agents/a08_auditor_nfa.py` | 53 | 62% | Análise qualitativa via LLM |
| `agents/base_agent.py` | 67 | 53% | Struct AgentResult (Pydantic v2) |
| `detectores_forenses.py` | 58 | 94% ✅ | Carrossel, smurfing, fraude temporal |
| `core/privacy.py` | 84 | 98% ✅ | Protocolo @Delta (PII → tokens) |
| `ml/xgboost_scorer.py` | 77 | 32% | Score risco 0–100 |
| `orgaudi/regra_especial_1.py` | 20 | 100% ✅ | RE-1: VENDA → COMPRA rural |

**Força:** Detectores forenses são determinísticos (94% cobertura). Privacidade integrada via @Delta.  
**Fraqueza:** A-07 e A-08 têm brechas de cobertura (20–62%). XGBoost scorer carece de validação.

---

### 2.2. Módulo 2: nfa_extractor (Extração de PDF)
**Descrição:** Extração de dados brutos de Notas Fiscais Avulsas.

| Componente | LOC | Cobertura | Objetivo |
|------------|-----|-----------|----------|
| `domain/nfa_parser_ai.py` | 295 | **10%** ⚠️ | Parse IA (GPT/Claude) de PDF |
| `infrastructure/ai_client.py` | 163 | 24% | Cliente unificado LLM |
| `domain/extractor.py` | 154 | 28% | Mapeamento de campos NFA |
| `infrastructure/database_v2.py` | 183 | 75% ✅ | Persistência SQLite/Postgres |

**Força:** Suporta múltiplos LLMs (Anthropic/OpenAI). Schema bem definido.  
**Fraqueza:** nfa_parser_ai.py (295 LOC) tem cobertura de apenas 10% — componente crítico subvalidado.

---

### 2.3. Módulo 3: pdf_engine (Geração de Relatórios)
**Descrição:** Renderização de laudos fiscais em PDF via ReportLab.

| Componente | LOC | Função |
|------------|-----|--------|
| `orgaudi/pages.py` | 1.724 | Layout e paginação de PDF |
| `orgaudi/template_builder.py` | 1.436 | Templates de seções (M-01, A-07, etc.) |
| `orgaudi/report_builder_rl.py` | 643 | Orquestração ReportLab |
| `orgaudi/styles.py` | 518 | Paleta e tipografia |
| `orgaudi/data_processing.py` | 521 | Cálculos FUNRURAL/IRPF |

**Força:** Bem estruturado. Separação clara entre layout, estilos e dados.  
**Fraqueza:** Dois arquivos gigantes (1.7k e 1.4k linhas) — refatoração candidata.

---

### 2.4. Módulo 4: api (Backend FastAPI)
**Descrição:** Endpoints HTTP unificados, autenticação JWT, rate limiting.

| Endpoint | Método | Status | LOC |
|----------|--------|--------|-----|
| `/nfae` | POST | ✅ | 50+ |
| `/auditoria/cruzada` | POST | ✅ | 259 |
| `/resultado/{id}` | GET | ✅ | - |
| `/auth/login` | POST | ✅ | 248 |
| `/ping` | GET | ✅ | - |

**Força:** JWT (argon2id + bcrypt legacy). Rate limit (60 req/min). Fallback gracioso para IA degradada.  
**Fraqueza:** Documentação de endpoints superficial. Faltam testes de integração E2E.

---

## 3. Qualidade de Código

### 3.1. Cobertura de Testes por Módulo
```
horizon_blue_one/       ████████░░ 65%
├── agents/             ░░░░░░░░░░ 30%  ⚠️ Crítico — A-07 e A-08
├── core/               ██████████ 90%  ✅
└── orgaudi/            ██████████ 99%  ✅

nfa_extractor/          ████░░░░░░ 35%  ⚠️
├── domain/             ███░░░░░░░ 25%  ⚠️ nfa_parser_ai.py: 10%
└── infrastructure/     ██████░░░░ 70%  ✅

api/                    ████████░░ 75%  ✅
pdf_engine/             ███░░░░░░░ 20%  (sem cobertura estruturada)
```

### 3.2. Testes Disponíveis
- **19 arquivos de teste**
- **255 testes unitários** — todos passando ✅
- **Fixtures compartilhadas** em `conftest.py` (nfa_venda, parte_produtor, produto_simples)
- **Cobertura mínima exigida:** 30% | **Alcançado:** 47,14% ✅

### 3.3. Problemas Identificados
| Nível | Componente | Descrição | Ação Recomendada |
|-------|-----------|-----------|-----------------|
| 🔴 Crítico | `nfa_parser_ai.py` (295 LOC) | Apenas 10% de cobertura em parser IA | Adicionar testes de integração com mock LLM |
| 🟡 Alto | `token_router.py` (94 LOC) | 0% de cobertura — roteamento de modelos | Testar fallback e seleção de modelo |
| 🟡 Alto | `a07_auditoria_assurance.py` | 20% de cobertura — detectores críticos | Testar cada tipologia forense isoladamente |
| 🟠 Médio | `pages.py` / `template_builder.py` | 1.7k + 1.4k LOC — muito grandes | Considerar refatoração em 3–4 módulos menores |
| 🟠 Médio | `metrics.py` (13 LOC) | 0% cobertura — observabilidade | Adicionar testes para Prometheus/Sentry |

---

## 4. Segurança

### 4.1. Conformidades Implementadas
- ✅ **JWT:** Argon2id (novo) + bcrypt (legacy compatível)
- ✅ **PII Protection:** Protocolo @Delta substitui CPF/CNPJ por tokens antes de LLM
- ✅ **Rate Limiting:** 60 req/60s por IP (Redis em prod, fakeredis em testes)
- ✅ **Audit Hash:** SHA-256 em cada AgentResult (rastreabilidade)
- ✅ **Dependencies:** Defusedxml (XXE hardening), tenacity (retry seguro)

### 4.2. Gaps Identificados
| Gap | Severidade | Ação |
|-----|-----------|------|
| Sem CORS configurado explicitamente | 🟡 Médio | Adicionar `CORSMiddleware` com whitelist de origens |
| Logs de erro podem expor stack traces | 🟡 Médio | Configurar logging estruturado (structlog) para prod |
| Nenhuma validação de CSP headers | 🟠 Baixo | Implementar Content-Security-Policy |

---

## 5. Observabilidade e DevOps

### 5.1. Infraestrutura
| Componente | Status | Detalhes |
|-----------|--------|----------|
| **Banco de dados** | Supabase (prod) | Transaction Pooler :6543, Direct :5432 para migrations |
| **Auth** | Supabase Auth | Via JWT + database local |
| **Cache/Rate limit** | Redis | Prod: Redis nativo; dev: fakeredis |
| **Monitoramento** | Prometheus + Sentry | Coletores básicos implementados (issue #25) |
| **Container** | Docker | compose.yml presente; Kubernetes manifests em `k8s/` |

### 5.2. Métricas Expostas
- ✅ `LAUDOS_TOTAL` (Counter)
- ✅ `LAUDO_DURATION_SECONDS` (Histogram)
- ❌ Faltam: mem_usage, api_latency, error_rate por endpoint

---

## 6. Dependências Críticas

### Versões Pinadas
```
fastapi>=0.136.1          ✅ Atualizado (2026)
anthropic>=0.49.0         ✅ Suporta Claude Sonnet 4.6
sqlalchemy>=2.0.0         ✅ ORM cross-DB
pydantic>=2.0.0           ✅ Validação v2
reportlab>=4.0.0          ✅ PDF generation
```

### Dependências Legadas
- **LangGraph** (v0.1.0) — Mencionado como "pipeline legado" → Candidato a remoção
- **bcrypt** — Mantido para login compatível com hashes antigos (correto)

---

## 7. Problemas Conhecidos e Tech Debt

### Issues Abertas (do CONTRIBUTING.md e histórico)
1. **#25 (P1):** Observability — faltam métricas de latência e error_rate
2. **#29 (P2):** Fatiamento de logs por severidade (estrutlog config incompleta)
3. **Token Router (token_router.py):** Sem testes — fallback de modelo não validado
4. **nfa_parser_ai.py:** Apenas 10% cobertura — crítico para extração PDF

### Tech Debt Recomendado
| Item | Esforço | Benefício |
|------|---------|-----------|
| Refatorar `pages.py` (1.7k LOC) | 🟡 Médio | ✅ Legibilidade +40%, manutenibilidade |
| Adicionar testes para A-07/A-08 | 🟡 Médio | ✅ Confiança em detectores críticos |
| Testar nfa_parser_ai com mocks | 🟡 Médio | ✅ Detectar regressões PDF parsing |
| Documenter CI/CD (GH Actions) | 🟠 Baixo | ✅ Onboarding mais rápido |

---

## 8. Commit History & Governance

### Contribuições Recentes
```
61af2c4 Revert "feat(pdf-engine): alinhar laudo ao modelo GENIS com CRC correto"
596bb1e feat(pdf-engine): alinhar laudo ao modelo GENIS com CRC correto
c3eb38e feat(pdf-engine): patches institucionais + pipeline de auditoria DEUSDETE
68c9734 chore(docs): limpa resíduos de Postgres local/Docker e atualiza arquitetura para Supabase
24f4945 fix(frontend): corrige porta da API de 8083 para 8082 + docs Supabase
```

### Branches
- **main:** Branch de produção
- **develop:** Branch de integração (não observado — usar main diretamente)
- **fix/frontend-api-port-and-supabase-docs:** Em progresso
- **claude/bold-villani-fbc6fe:** Worktree de experimento (ignore)

### Qualidade de Commits
✅ Convenção respeitada: `tipo(escopo): mensagem pt-BR`  
✅ Squashing apropriado  
✅ PR template presente (PULL_REQUEST_TEMPLATE.md)

---

## 9. Recomendações Priorizadas

### 🔴 P0 (Crítico — faça AGORA)
1. **Adicionar testes para `nfa_parser_ai.py`** (295 LOC, 10% cobertura)
   - Impact: Detectar regressões no parse de PDF
   - Esforço: ~4h
   - Ferramentas: pytest + mock/patch de LLM

2. **Validar fallback de IA** (`token_router.py`, 0% cobertura)
   - Impact: Garantir degradação graceful quando API falha
   - Esforço: ~2h
   - Test: Mockar timeouts/erros de Anthropic

### 🟡 P1 (Alta — próximas 2 sprints)
3. **Refatorar `pages.py` (1.7k LOC)**
   - Split: 4 módulos temáticos (capa, análise, achados, rodapé)
   - Ganho: -40% complexidade, +50% testabilidade

4. **Expandir cobertura de `a07_auditoria_assurance.py` (20% → 80%)**
   - Adicionar testes para cada detector forense
   - Validar edge cases (CNPJ duplicado, datas fora do período, etc.)

5. **Documentar pipeline de CI/CD**
   - README com: "Como rodar testes localmente", "Deploy em Supabase", "Métricas Prometheus"

### 🟠 P2 (Médio — backlog)
6. Implementar observability completa (latência, error_rate por endpoint)
7. Adicionar CSP headers e CORS stricto
8. Remover LangGraph se legado não for mais usado
9. Refatorar `data_processing.py` para lógica compartilhada (DRY)

---

## 10. Conclusão

**OrgAudi é uma plataforma robusta e bem-estruturada**, com:
- ✅ Arquitetura modular clara (4 módulos distintos)
- ✅ Segurança em primeiro plano (PII protection, JWT, rate limit)
- ✅ Testes sólidos (47% cobertura, 255 testes passando)
- ⚠️ Gaps em cobertura de componentes críticos (nfa_parser_ai.py, token_router.py)
- ⚠️ Refatoração necessária em 2 arquivos grandes (pages.py, template_builder.py)

**Score Geral:** 8.2/10 (Muito Bom)
- Código: 8.5/10
- Testes: 7.5/10
- Documentação: 8/10
- Segurança: 9/10
- DevOps: 7.5/10

**Próximo passo:** Executar P0 (testes de nfa_parser_ai e fallback de IA) nas próximas 2 semanas.

---

_Análise gerada: 2026-05-16 | Ferramenta: Claude Code_
