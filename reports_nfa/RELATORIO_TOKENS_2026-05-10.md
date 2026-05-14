# Plano de Redução de Tokens — Horizon-Blue One

**Data:** 2026-05-10
**Base:** lote LLM real `llm_alto_risco_1778418321.json` + observações em `_MODELO_BASE` do `token_router.py`

## Diagnóstico — uso real por agente (médias)

| Agente | Modelo | tokens_in | tokens_out | max_tokens (antes) | Custo/chamada |
|--------|--------|-----------|------------|--------------------|---------------|
| S1 sentinel  | Haiku  | 119  | 336   | 512   | $0.0014 |
| S2 forense   | Sonnet | 151  | 1500  | 2048  | $0.0230 |
| S3 fiscal    | (skip-LLM determinístico) | — | — | — | $0 |
| S4 contábil  | (não rodou no teste)      | — | — | 1536 | — |
| S5 nfa       | **Opus** | 390 | 600 | 1536  | **$0.0509** |
| S6 rh        | (não rodou no teste)      | — | — | 1024 | — |
| S7 ceo       | Sonnet | 150  | 1100  | 2048  | $0.0170 |

**Total por produtor FULL:** ~$0.092 (60% só do S5 em Opus).

## Achado crítico

`core/token_router.py:96`
```python
TipoTarefa.AUDITORIA: ModelType.OPUS,     # A-08 @Auditor-NFA
```

Mas em `_AGENTE_TAREFA` (linha 174-178) o **comentário** diz "Sonnet":
```python
"S3": TipoTarefa.AUDITORIA,           # @Fiscal    → Sonnet
"S4": TipoTarefa.AUDITORIA,           # @Contabil  → Sonnet
"S5": TipoTarefa.AUDITORIA,           # @NFA       → Sonnet
```

Inconsistência entre intenção declarada (Sonnet) e implementação (Opus). Fica como item #1 abaixo (precisa OK do usuário porque muda comportamento de todos os agentes AUDITORIA).

---

## Cortes implementados nesta sessão (commit pendente)

### 1. `s5_nfa.py` — `max_tokens` 1536 → **768** + system "RESPOSTA CONCISA"
Uso real: 600 tokens out. Margem 28%.
```python
"RESPOSTA CONCISA: liste no máximo 5 divergências e 3 riscos, sem comentários extras."
```

### 2. `s7_ceo.py` — `max_tokens` 2048 → **1280** + system limites por campo
Uso real: 1100 tokens out. Margem 16%.
```python
"RESPOSTA CONCISA: parecer_juridico até 4 linhas, mda_executivo até 6 linhas, "
"máx 5 acoes_imediatas e 5 riscos_residuais. Sem prefácio."
```

### 3. `s2_forense.py` — `max_tokens` 2048 → **1700** + system "narrativa em 8 linhas"
Uso real: 1500 tokens out. Margem 13%.
```python
"RESPOSTA CONCISA: narrativa em até 8 linhas, máx 5 evidencias e 5 acoes, sem repetições."
```

**Economia estimada (output):** ~30% no S5/S7 quando o modelo seguir a instrução de concisão (Anthropic costuma respeitar). Em lote de 20 produtores FULL: **~$0.40-0.55/lote**.

> Nota: reduzir `max_tokens` sozinho não corta custo (Anthropic cobra os tokens efetivamente gerados, não o limite). O ganho real vem da instrução de concisão no system prompt — `max_tokens` é só *proteção* contra blow-up.

---

## ⚡ Redistribuição executada (rev 2026-05-11)

Aplicada na sessão seguinte ao usuário aprovar a redução. Mudanças em
`horizon_blue_one/core/token_router.py`:

### Mix-alvo: **90 / 8 / 2** (antes 80 / 15 / 5)

```python
_MODELO_BASE = {
    # HAIKU — operação simples (mantém)
    ROTEAMENTO, CLASSIFICACAO, EXTRACAO, LGPD, CONFORMIDADE,
    ICMS, ITR, LCDPR, PLANEJAMENTO, ESOCIAL, PATRIMONIO : HAIKU
    # SONNET — raciocínio cruzado
    AUDITORIA  : SONNET    # rev 2026-05-10: era OPUS
    FORENSE    : SONNET
    JURIDICO   : SONNET
    # OPUS — só escalada por critério
    FORENSE_CRITICO, DECISAO_FINAL : OPUS
}
```

### Novo downgrade Sonnet → Haiku (mais agressivo)

Auditoria operacional (`AUDITORIA`, `ICMS`, `ITR`, `LCDPR`, `ESOCIAL`) cai
para Haiku quando `score_risco < 50` e `tipologias_criticas == 0`.

`FORENSE` / `JURIDICO` / `DECISAO_FINAL` ficam fora — exigem raciocínio
cruzado mesmo em caso limpo.

### Escalada Opus preservada (em `rotear()`)

Sonnet → Opus quando:
- `score_risco >= 85`
- `tipologias_criticas >= 3`
- `probabilidade_autuacao >= 75%`

### Simulação no lote real (20 produtores)

| Agente | Antes (mix antigo)            | Depois (mix novo)            |
|--------|-------------------------------|------------------------------|
| S5     | 20 × Opus                     | 19 × Sonnet + 1 × Opus (GEAN) |
| S7     | 18 × Sonnet + 1 × Opus (upg)  | 19 × Sonnet + 1 × Opus (GEAN) |
| S2     | 3 × Sonnet                    | 3 × Sonnet                    |
| S1     | 3 × Haiku                     | 3 × Haiku                     |

### Economia projetada

| Cenário | Custo/lote (20 produtores) |
|---------|---------------------------|
| Lote 2026-05-10 (Opus base AUDITORIA) | **$1,2164** |
| Após redistribuição (Sonnet base, escalada Opus) | **~$0,55** (-55%) |
| + Item #2 (prompt caching) | ~$0,47 (-61%) |
| + Item #3 (PF_GATE 0,55) | ~$0,38 (-69%) |

### Testes pós-mudança
- `test_sprint_smoke.py` : 10/10 ✓
- Roteamento simulado para 20 casos do lote real: comportamento confere
  (Sonnet padrão + Opus escalado apenas em GEAN)

---

## Próximos passos (já aplicados ou pendentes)

### #1 — ✅ APLICADO em 2026-05-11 — `AUDITORIA: OPUS → SONNET`

`token_router.py:96`:
```python
TipoTarefa.AUDITORIA: ModelType.SONNET,   # antes: OPUS
```

Mantém escalada automática para Opus quando `score_risco >= 85` ou `tipologias_criticas >= 3` ou `prob_autuacao >= 75%` (já implementada nas linhas 224-244). Casos críticos continuam Opus; auditoria padrão cai para Sonnet.

**Impacto:** S5 cai de $0.051 → $0.010/chamada (5×). Em lote de 20 produtores: **economia de ~$0.82/lote** (~50% do custo total).

**Risco:** baixo. Os 3 critérios de escalada já cobrem casos críticos. Bate com o comentário declarado do código.

**Validação:** rodar `test_llm_alto_risco` antes/depois e comparar pareceres dos 3 produtores fronteira (GERALDO, FABIO, ETERVALDO).

### #2 — Prompt caching (Anthropic API feature)

Adicionar `cache_control={"type": "ephemeral"}` no system prompt dos agentes Sonnet/Opus quando ≥1024 tokens. Anthropic cacheia o prefixo por 5 min (TTL).

- Cache hit: input desconta 90% do custo.
- Para lote sequencial: a partir do 2º produtor, custo de input despenca.
- Implementação: `model_adapter.py` precisa passar `system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}]`.

**Economia estimada:** S2 e S7 têm system grande; em lote de 20 produtores, economiza ~$0.05-0.10/lote.

### #3 — Aumentar `PF_GATE_REDUZIDO` de 0.65 para 0.55

Mais produtores no caminho REDUZIDO (sem S1+S2). Pelos dados do teste, REDUZIDO economiza ~$0.025/produtor (sem S2 forense em Sonnet).

**Risco:** médio. Casos pf 0.55-0.65 perdem detecção forense (S2). Validar contra falsos negativos antes de aplicar.

### #4 — Mover S2 (forense) base de Sonnet para Haiku quando `score_risco < 60`

Forense leve (score baixo, sem detectores) não precisa Sonnet. Routing condicional:
```python
if score_risco < 60 and not any(detectores.values()):
    modelo_base = ModelType.HAIKU
```

**Risco:** baixo. Casos limpos têm fallback determinístico já (skip-LLM em S2).

### #5 — Agregar S5+S7 num único prompt para casos REDUZIDOS

Quando o pipeline é só `S3+S5+S7`, mesclar S5 e S7 numa chamada única ao Opus (ou Sonnet com #1) com system combinado.

**Economia:** -1 chamada por produtor REDUZIDO. Em lote típico (17 produtores REDUZIDO): **~$0.17/lote** + redução de latência (50s → 30s/produtor).

**Risco:** alto. Quebra a separação de responsabilidades. Implementar só se #1-4 forem insuficientes.

---

## Resumo da projeção

| Cenário | Custo/lote (20 produtores) |
|---------|---------------------------|
| Atual (sem cortes desta sessão) | ~$1.84 |
| Com cortes desta sessão (#1-3 implementados) | ~$1.30 (-29%) |
| + Item #1 (Opus→Sonnet AUDITORIA) | ~$0.48 (-74%) |
| + Item #2 (prompt caching) | ~$0.40 (-78%) |
| + Item #3 (PF_GATE 0.55) | ~$0.32 (-83%) |

Próximo passo recomendado: aprovar #1 e validar com rodada de teste real.
