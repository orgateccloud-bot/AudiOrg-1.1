# OrgAudi — Arquitetura

Sistema de auditoria fiscal soberana para NFA-e (Notas Fiscais Avulsas eletrônicas) e
documentos GIEF/SEFAZ-GO. Combina extração híbrida (regex + LLM), squad multi-agente
e roteamento de custo por tarefa.

---

## 1. Visão geral

```
┌──────────────────────────────────────────────────────────────────┐
│  Frontend (React 19, Vite)                                       │
│  └── chama FastAPI                                               │
└────────────────────────────┬─────────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────────┐
│  api/  — FastAPI + JWT + Prometheus                              │
│  ├── routes/      → endpoints (auditoria, agente, finance...)    │
│  ├── services/    → orquestração de pipeline (gate estrito)      │
│  ├── auth/        → JWT + blacklist Redis                        │
│  └── middleware/  → CSP nonce, rate-limit, structured logs       │
└────────────────────────────┬─────────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────────┐
│  horizon_blue_one/  — squad multi-agente + core                  │
│  ├── core/         → orchestrator, token_router, precalc, ledger │
│  ├── agents/       → S1–S7 (waves) + A-* (assurance/auditoria)   │
│  ├── ml/           → xgboost_scorer, lstm_scorer                 │
│  ├── orgaudi/      → regra_especial_1, resumo_fiscal (F1–F6)     │
│  └── tools/        → mcp_bridge (allowlist YAML)                 │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                ┌────────────┴────────────┐
                │                         │
┌───────────────▼─────────┐   ┌───────────▼────────────────────────┐
│ nfa_extractor/          │   │ pdf_engine/orgaudi_v4/             │
│ Parser híbrido          │   │ Builder de laudo PDF (ReportLab)   │
│ regex → Claude          │   │ 11 páginas, hash de integridade    │
└─────────────────────────┘   └────────────────────────────────────┘
```

---

## 2. Camadas

### `api/`
Camada HTTP. Cada rota delega para `services/`. **Gate moderado** em `api/services/`:
ruff com `ASYNC, TRY, RET, SIM, PIE, PERF, PTH, PLE, T20`. Não usa mypy strict.

### `horizon_blue_one/core/`
Núcleo de orquestração. **Gate estrito** (`scripts/lint_core_strict.py`):
- ruff `--select ALL` (com `extend-ignore` mínimo)
- mypy `--strict`
- enforced por `pre-push` hook e CI (`core-strict-gate`)

Módulos:
- `orchestrator.py` — coordena agentes em paralelo via `asyncio.gather`, propaga
  resultados entre etapas, publica eventos no `EventBus` (asyncio.Queue + subscribers).
- `token_router.py` — roteamento de modelos por tipo de tarefa (ver §4).
- `precalc.py` — pré-cálculo determinístico (regex PII, validação CPF/CNPJ, IE,
  pendências documentais, XGBoost score, LSTM). Resultado cached em
  `payload["__precalc__"]`. Cada agente lê dali em vez de recomputar.
- `prompt_compactor.py` — compacta payload p/ LLM (kv-list, top-N notas).
- `privacy.py` — redação de PII antes de enviar para LLM.
- `ledger.py` — log assíncrono auditável (estrutura JSON-lines).

### `horizon_blue_one/agents/`
Squad em **7 ondas** (S1–S7), cada onda agregando múltiplos agentes legados:

| Wave | Codinome     | Substitui                                   | Modelo  |
|------|--------------|---------------------------------------------|---------|
| S-1  | @Sentinel    | A-02 Protetor + A-03 ZeroTrust + A-09 TI + A-16 LGPD | Haiku   |
| S-2  | @Forense     | A-07 Assurance + AN-01..AN-18               | Sonnet  |
| S-3  | @Fiscalista  | ICMS, ITR, LCDPR, planejamento              | Sonnet  |
| S-4  | @Contabil    | classificação, F1–F6, deduções              | Haiku   |
| S-5  | @NFA         | A-08 Auditor-NFA (núcleo)                   | Sonnet/Opus |
| S-6  | @RH          | eSocial, folha rural                        | Haiku   |
| S-7  | @CEO         | A-00 Decisão final + A-18 Resumo            | Opus    |

Cada agente herda de `BaseAgent` (Pydantic V2). `AgentResult` carrega `audit_hash`
SHA-256 do output canonicalizado — base do trilho de integridade.

### `horizon_blue_one/ml/`
- `xgboost_scorer.py` — score de risco fiscal 0–100, modo treinado ou heurístico.
- `lstm_scorer.py` — anomalia temporal por produtor. Heurística por padrão; PyTorch
  treinado via env `LSTM_MODEL_PATH`.

### `horizon_blue_one/orgaudi/`
Regras de negócio determinísticas:
- `regra_especial_1.py` — reclassifica VENDA → COMPRA quando produtor rural é
  destinatário (RE-1, simétrica à NF-e do comprador).
- `resumo_fiscal.py` — apura F1–F6 (Receita Imediata, Trânsito, Receita Bruta,
  Despesa, Resultado Rural, FUNRURAL/IRPF).

### `nfa_extractor/`
Parser híbrido de PDF GIEF/SEFAZ-GO:
1. `_extrair_texto_pymupdf` → PyMuPDF (rápido, gratuito)
2. `_split_blocos` → divide por `IDENTIFICAÇÃO DA NOTA`
3. `_parse_bloco_regex` → tenta regex; aceita se `confianca >= 0.70`
4. `_parse_lote_claude` → fallback Claude Haiku para blocos ambíguos
5. dedup + sort + período + estatísticas

### `pdf_engine/orgaudi_v4/`
Builder de laudo PDF (ReportLab). 11 páginas: capa, achados, recomendações,
fórmulas, testes, catálogo, planilhas mensais, compras, assinatura/hash.

---

## 3. Pipeline NFA-e (produção)

```
Input: list[NotaFiscal] + Contribuinte
   │
   ▼
[1] RE-1            → reclassifica VENDA↔COMPRA simétricas (regra determinística)
   │
   ▼
[2] XGBoost Score   → 0–100, nível CRÍTICO/ALTO/MÉDIO/BAIXO
   │
   ▼
[3] F1–F6 Apuração  → resumo fiscal (heurístico, NumPy)
   │
   ▼
[4] A-07 Assurance  → análise forense (Sonnet), tolerante a falha
   │
   ▼
[5] A-08 Auditor    → decisão final + audit_hash (Sonnet ou Opus por escalada)
```

Pipeline em `api/services/auditoria_nfae.py::processar_nfae`.

---

## 4. Roteamento de modelos (mix 80/15/5)

Política em `horizon_blue_one/core/token_router.py` (rev 2026-05-09):

| Modelo  | Custo (USD/MTok in/out) | Mix-alvo | Casos                                          |
|---------|--------------------------|----------|------------------------------------------------|
| Haiku   | 0.80 / 4.00              | 80%      | Roteamento, classificação, extração, LGPD, ICMS, ITR, LCDPR, eSocial, conformidade |
| Sonnet  | 3.00 / 15.00             | 15%      | Assurance, anomalias AN-01..18, forense de grafo, jurídico complexo |
| Opus    | 15.00 / 75.00            | 5%       | Apenas A-08 @Auditor-NFA + A-00 @CEO (decisão final) |

**Escalada para Opus** (override do mix):
- AUDITORIA com `score >= 85`
- AUDITORIA com `prob. autuação >= 0.75`
- 3+ tipologias críticas
- Tipo `FORENSE_CRITICO` ou `DECISAO_FINAL` (sempre Opus)

**Downgrade Sonnet → Haiku** (em tarefas operacionais, score < 50, volume ≤ 5):
ativa para `AUDITORIA, ICMS, ITR, LCDPR, ESOCIAL` (frozenset
`_TAREFAS_OPERACIONAIS_HAIKU`). `FORENSE`, `JURIDICO` e `DECISAO_FINAL` não
descem nunca.

---

## 5. Gates de qualidade

### Camada `horizon_blue_one/core/` — gate **estrito**
`scripts/lint_core_strict.py`:
- `ruff --select ALL` + `extend-ignore` curado
- `mypy --strict` (com overrides em `pyproject.toml`)
- Hook `.git/hooks/pre-push` (instala via `python scripts/install_git_hooks.py`)
- CI job `core-strict-gate` (`.github/workflows/ci.yml`)

### Camada `api/services/` — gate **moderado**
`api/services/ruff.toml`:
- Herda da raiz (`extend = "../../ruff.toml"`)
- `extend-select` foco anti-bug + I/O: `ASYNC, TRY, RET, SIM, PIE, PERF, PTH, PLE, T20`
- Sem mypy strict

### Demais camadas — gate **baseline**
`ruff.toml` na raiz: `E, F, I, B, UP, S, RUF` com per-file-ignores documentados.

### Cobertura de testes
- 659 testes em `tests/` (cobertura 99.13%)
- `requires-coverage = 30%` em `pyproject.toml`
- Pre-push hook roda `pytest -q` antes de permitir push

---

## 6. Segurança

- **CSP nonce dinâmico** por request (`api/middleware/csp.py`)
- **JWT blacklist** em Redis (`api/auth/`)
- **PII redaction** antes de enviar para LLM (`core/privacy.py`)
- **MCP allowlist YAML** (`tools/mcp_bridge.py`) — tabelas/colunas vêm de lista branca
- **Audit hash SHA-256** em todo `AgentResult` (trilho de integridade)
- **Bandit** ativo via ruff (`S` rules)
- **md5 não-criptográfico** marcado com `usedforsecurity=False` + comentário

---

## 7. Variáveis de ambiente críticas

```
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
SQUAD_MODEL=anthropic:claude-sonnet-4-6
AUDITORIA_MODEL=anthropic:claude-sonnet-4-6
AUDITORIA_MODEL_SIMPLES=anthropic:claude-haiku-4-5-20251001
LSTM_MODEL_PATH=          # opcional — ativa LSTM treinado
NFA_REPO_PATH=D:\nfa-repo
```

---

## 8. Como rodar

```bash
# Backend + frontend
./run_fullstack.bat              # backend :8081 + frontend :5173

# Apenas testes
python -m pytest tests/ -q

# Gate estrito (manual)
python scripts/lint_core_strict.py

# Instalar pre-push hook
python scripts/install_git_hooks.py
```

---

## 9. Decisões arquiteturais

- **Mix 80/15/5** — alvo de custo, não regra rígida. Opus reservado a auditoria
  final + decisão CEO.
- **Pré-cálculo no `precalc.py`** — agentes leem cache, não recomputam. Reduz
  custo de tokens (envia menos contexto para LLM).
- **Squad em waves S-1..S-7** — substitui squad legado A-01..A-32 (mantida em
  `agents/_legacy/`). Reduz overhead de orquestração; cada wave agrega agentes
  legados afins.
- **EventBus assíncrono** — A-00 @CEO reage a `ESCALADO` automaticamente, em vez
  de polling.
- **Gate em duas camadas** — core estrito (zero tolerância), api/services
  moderado (foco em bugs e I/O assíncrono), resto baseline.
- **Tokenize-based rename** em `pdf_engine/orgaudi_v4` (I → story) — preserva
  strings/comentários.
