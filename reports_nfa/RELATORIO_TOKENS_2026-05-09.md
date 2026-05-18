# Relatório de Tokens & Melhoramentos — Horizon-Blue / OrgAudi

**Repositório:** `orgateccloud-bot/AudiOrg-1.1`
**Branch:** `feat/orchestrator-mix-80-15-5`
**Commit base:** `231d660` (consolida 28 agentes em S1..S7)
**Data:** 2026-05-09
**Escopo:** mapeamento completo + análise de consumo de tokens + roadmap de melhoria, antes do teste real com créditos Anthropic.

---

## A. Mapa do projeto

### Estrutura tracked (59 arquivos, 3 185 LOC core)

```
horizon_blue_one/
  agents/
    base_agent.py                    131  Pydantic V2 + audit_hash + parse_json + retry
    detectores_forenses.py            84  5 detectores deterministicos (carrossel, smurf...)
    a_token.py                       170  call_otimizado (router + retry + estatisticas)
    s1_sentinel.py                    91  LGPD + ZeroTrust + TI            (Haiku)
    s2_forense.py                    119  Anomalias + Assurance + Grafo    (Sonnet/Opus)
    s3_fiscal.py                     113  ICMS + ITR + LCDPR + CFOP        (Sonnet)
    s4_contabil.py                    98  Patrimonio + biologicos + caixa  (Sonnet)
    s5_nfa.py                        100  Auditoria nucleo NFA-e           (Sonnet)
    s6_rh.py                          87  eSocial isolado                  (Sonnet)
    s7_ceo.py                        106  Governanca + juridico + MD&A     (Sonnet/Opus)
    _legacy/                              28 agentes A-XX preservados (rollback/regressao)
  core/
    config.py                         90  cascade env -> config.env -> .env
    ledger.py                         74  audit log persistente
    model_adapter.py                  98  Anthropic + retry + prompt cache ephemeral
    orchestrator.py                  334  pipeline paralelo + early-exit + budget
    precalc.py                       353  10 funcoes deterministicas em parallel async
    privacy.py                        34  utilidades LGPD
    prompt_compactor.py               75  kv / tsv / flags / resumo_detectores
    token_router.py                  371  rotear() + stats + custos + max_tokens
  ml/
    xgboost_scorer.py                229  scorer heuristico + cache de detectores
  nfa_bridge/__init__.py             219  CFOP heuristico + agrupamento por produtor
  orgaudi/
    anomalias.py                      75
    regra_especial_1.py               62  RE-1: VENDA->COMPRA quando produtor=DEST+rural
    resumo_fiscal.py                  73
  tests/
    test_pdf_real.py                       auditoria por produtor (sem LLM)
    test_sprint_smoke.py                   10 smoke tests (precalc/compactor/memo/RE-1)
    test_llm_alto_risco.py                 S1..S7 sobre 6 ALTO risco (sem credito atual)
```

### Pipeline atual

```
PDFs por produtor
    -> nfa_bridge.processar_produtor()        # extrai + posicao por arquivo + CFOP heuristico
    -> precalc.precalcular()                  # 10 fns determ. em parallel + memo TTL 5min
        |-- _re1_classifier (RE-1)
        |-- _pii_scanner / _doc_validator
        |-- _detectores_all (5 detectores)
        |-- _xgboost_score / _cfop_validator
        |-- _lcdpr_diff / _itr_capacidade
        |-- _grafo_metrics / _caixa_aggregator
    -> orchestrator.executar_pipeline()
        if audit_limpa: EARLY_EXIT (zero LLM)
        else:           gather(S1..S6) -> S7 (CEO ultima)
                       cada Sx tem skip-LLM proprio se precalc verde
```

---

## B. Métricas atuais (estimativa, ~4 chars/token)

### B.1 Tokens por agente — caso "fica no skip-LLM" (verde determinístico)

| Agente | System | Prompt | Total in | Cobra LLM? |
|---|---:|---:|---:|---|
| S1 Sentinel  |  72 |   0 |   0 | nao |
| S2 Forense   |  78 |   0 |   0 | nao |
| S3 Fiscal    |  97 |   0 |   0 | nao |
| S4 Contabil  |  80 |   0 |   0 | nao |
| S5 NFA       |  85 |   0 |   0 | nao |
| S6 RH        |  63 |   0 |   0 | nao |
| S7 CEO       |  88 |   0 |   0 | nao (early-exit pula tudo) |

### B.2 Tokens por agente — caso "passa para LLM" (caso típico ALTO risco)

| Agente | System | Prompt | Max-out | Modelo | Custo-in | Custo-out |
|---|---:|---:|---:|---|---:|---:|
| S1 Sentinel | 72 | ~50 | 512  | Haiku  | $0.0000010 | $0.0020 |
| S2 Forense  | 78 | ~150 | 2048 | Sonnet | $0.0000007 | $0.0307 |
| S3 Fiscal   | 97 | ~200 | 2048 | Sonnet | $0.0000009 | $0.0307 |
| S4 Contabil | 80 | ~300 | 1536 | Sonnet | $0.0000011 | $0.0230 |
| S5 NFA      | 85 | ~400 | 1536 | Sonnet | $0.0000015 | $0.0230 |
| S6 RH       | 63 | ~80  | 1024 | Sonnet | $0.0000004 | $0.0154 |
| S7 CEO      | 88 | ~250 | 2048 | Sonnet | $0.0000010 | $0.0307 |
| **Total/produtor (caso ALTO LLM)** | | | | | **~$0.000007** | **~$0.156** |

> Nota: custo-input está dominado pelo cache ephemeral hit (system reusable após primeira chamada — ~0.1× preço). Custo-output assume max_tokens preenchido.

### B.3 Custo extrapolado — 6 produtores ALTO risco

| Cenário | Custo USD | Custo BRL (~5.50) |
|---|---:|---:|
| Verde (early-exit total)        | $0.000   | R$ 0,00 |
| Caso real esperado (6 ALTO)     | $0.94    | R$ 5,17 |
| Pior caso (todos Sonnet, max-out)| $1.50   | R$ 8,25 |
| Pior caso com 3 escaladas Opus  | ~$3.00   | R$ 16,50 |

### B.4 Distribuição mix-alvo vs realizado

Mix-alvo: **80 Haiku / 15 Sonnet / 5 Opus**.

Realizado nos 7 consolidados (caso típico ALTO):
- Haiku: 1 (S1) = 14.3%
- Sonnet: 6 (S2..S7) = 85.7%
- Opus: 0 (escalada por score≥85, prob≥75% ou ≥3 tipologias críticas)

> O mix-alvo 80/15/5 foi calibrado para 28 agentes A-XX. Com 7 consolidados, **a distribuição natural fica 14/86/0** porque cada Sx encapsula trabalho de 4-6 A-XX. Não é regressão — é consequência da consolidação.

---

## C. Bugs identificados

### C.1 [CRÍTICO] s7_ceo.py:90 — NameError pendente

```python
linhas = []
...
resumo_txt = "\n".join(linhas) or "(sem agentes)"
...
data["resumo_agentes"] = resumo   # <-- 'resumo' nao existe; deveria ser 'resumo_txt'
```

**Impacto:** quando S7 finalmente conseguir rodar (créditos OK), levantará `NameError`. O AgentResult será marcado ERRO e o relatório consolidado não terá MD&A. **Não foi pego no teste atual porque a API retornou 400 antes do parse.**

### C.2 [MÉDIO] test_llm_alto_risco — `score_precalc=None`

O script lê `payload["__precalc__"]` ANTES de `executar_pipeline()`. Mas o orchestrator clona o payload internamente com `{**payload, "resultados_agentes": {}}` e injeta `__precalc__` apenas na cópia. O `payload` original do chamador permanece sem precalc.

**Mitigação:** chamar `precalcular(payload)` antes do orchestrator (memo cache TTL 5min evita recomputo) ou retornar payload modificado.

### C.3 [BAIXO] S1 não usa prompt_compactor

S1 emite `f"PII detectado: {pii}"` — Python serializa dict via `repr` (verboso, com aspas, espaços). `kv(pii)` reduziria ~35% no prompt-input.

### C.4 [BAIXO] Token router não mapeia S1..S7 em `_AGENTE_TAREFA`

`MAX_TOKENS_OTIMO` e `_AGENTE_TAREFA` só listam A-XX. Como os agentes Sx passam `tipo_tarefa=` e `max_tokens=` explícitos, não há regressão, mas o **registro estatístico fica menos rico** (não computa upgrade/downgrade por agente Sx) e o relatório de custo não diferencia S1 de S2.

---

## D. Oportunidades de melhoria (priorizadas por ROI)

| # | Item | Impacto tokens | Esforço | Prioridade |
|---|---|---:|---:|---|
| D1 | Corrigir bug s7_ceo `resumo` → `resumo_txt` | – | 1 min | **P0** |
| D2 | Mapear S1..S7 em `_AGENTE_TAREFA` + `MAX_TOKENS_OTIMO` | – | 5 min | **P0** |
| D3 | S1 usar `kv()` em PII e docs | -35% prompt-in S1 | 5 min | **P1** |
| D4 | Reaproveitar precalc no test_llm (passar payload já calculado) | -15s latência/produtor | 5 min | **P1** |
| D5 | Paralelizar produtores em `executar_lote` (asyncio.gather com semáforo) | -50% wall-time | 15 min | **P2** |
| D6 | Skip-LLM mais agressivo em S2 (sem `fornecedor_fantasma` ≤ 5 e score < 50) | -1 LLM-call/produtor médio | 5 min | **P2** |
| D7 | S7 receber `resumo_txt` apenas com agentes que ESCALARAM (não todos) | -30% prompt-in S7 | 10 min | **P2** |
| D8 | Schema Pydantic V2 nas respostas → validação 1-shot, sem retry F20 em 80% dos casos | -10% tokens médios | 30 min | **P3** |
| D9 | Cache do precalc compartilhado entre produtores irmãos (mesmo CPF em REM/DEST já é) | já feito | – | – |
| D10 | Reduzir `max_tokens` Sonnet 2048 → 1024 quando skip-LLM não dispara mas não há tipologia crítica | -50% custo-out | 10 min | **P2** |
| D11 | Logar `cache_read_input_tokens` da resposta Anthropic para medir economia real do cache | observabilidade | 10 min | **P3** |
| D12 | Calibrar threshold do detector `carrossel` (atualmente dispara em GEAN/JOSMAIR — verificar se FP) | acurácia | 30 min | **P3** |

### D2 detalhe — completar token_router

```python
# Adicionar em MAX_TOKENS_OTIMO:
"S1": 512,  "S2": 2048, "S3": 2048, "S4": 1536,
"S5": 1536, "S6": 1024, "S7": 2048,

# Adicionar em _AGENTE_TAREFA:
"S1": TipoTarefa.LGPD,
"S2": TipoTarefa.FORENSE,
"S3": TipoTarefa.AUDITORIA,
"S4": TipoTarefa.AUDITORIA,
"S5": TipoTarefa.AUDITORIA,
"S6": TipoTarefa.ESOCIAL,
"S7": TipoTarefa.JURIDICO,
```

### D5 detalhe — paralelizar produtores

```python
async def executar_lote(pasta_pdfs, atividade="bovino", max_paralelo=3):
    grupos = agrupar_pdfs_por_produtor(pasta_pdfs)
    sem = asyncio.Semaphore(max_paralelo)
    async def _um(produtor, pdfs):
        async with sem:
            payload = processar_produtor(produtor, pdfs, atividade)
            return await precalcular(payload) if payload else None
    return [r for r in await asyncio.gather(*(_um(p, q) for p, q in grupos.items())) if r]
```

### D7 detalhe — S7 recebe só agentes escalados

```python
# Em s7_ceo.py:
linhas = []
for aid, out in resultados.items():
    if not isinstance(out, dict): continue
    sub = {k: out.get(k) for k in chaves if k in out}
    # Filtra: so inclui agente que escalou ou tem alerta
    valores_relevantes = {k: v for k, v in sub.items()
                          if v not in ("OK", "CONFORME", None, "", [])}
    if valores_relevantes:
        linhas.append(f"{aid}: {kv(valores_relevantes)}")
```

---

## E. Próximos passos

1. **Aplicar D1 + D2 + D3 imediatamente** (8 min total, zero risco).
2. **Adicionar créditos Anthropic** em https://console.anthropic.com/settings/billing.
3. **Re-rodar `test_llm_alto_risco`** com 6 produtores ALTO. Esperado: 6 audits LLM em ~30-60 s, custo total ≈ $0.94. Memo cache do precalc (TTL 5 min) evita reprocessamento.
4. Validar `cache_read_input_tokens` na primeira resposta para confirmar prompt cache ativa.
5. Aplicar D5 + D7 + D10 num segundo passe se custo > $1/lote.

## F. Sumário executivo

- **Pipeline OK estruturalmente**: skip-LLM determinístico, prompt cache ephemeral, mix-alvo router.
- **1 bug crítico** (D1) bloqueando S7 — corrigir antes de gastar créditos.
- **Custo estimado por produtor ALTO**: ~$0.16 (6 LLM calls Sonnet com skip-LLM seletivo). Totalmente sustentável.
- **Custo agregado atual** (1 PDF de 1998 notas, 22 produtores) com early-exit em médio/baixo + LLM full nos 6 ALTO: **~R$ 5-8 por lote completo**.
- **Maior alavanca remanescente**: D5 (paralelização) reduz wall-time pela metade sem custo extra.
