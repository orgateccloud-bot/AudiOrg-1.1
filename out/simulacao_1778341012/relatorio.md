# Simulação NFE-Gado 2026 — Consumo de Tokens

**Pipeline:** `auditor` · **PDFs:** 3 · **Análises individuais:** 3 · **Análises consolidadas:** 2

## Resumo Executivo

| Métrica | Valor |
|---|--:|
| Custo total (mock) | USD 2.0287 |
| Baseline tudo-Sonnet | USD 0.5141 |
| **Economia absoluta** | USD -1.5146 |
| **Economia %** | **-294.62%** |
| Mix de modelos (Haiku/Sonnet/Opus) | 0.0% / 60.0% / 40.0% |
| Total de chamadas Claude | 25 |
| PDFs vazios (sem extração) | 0 |

## Tabela 1 — Consumo por PDF Individual (3)

| PDF | Notas | Valor (R$) | Tok IN | Tok OUT | Custo (USD) | Economia % |
|---|--:|--:|--:|--:|--:|--:|
| ADELA REM.pdf | 19 | 941,050 | 24,928 | 4,299 | 0.5851 | -320.1% |
| ADELA DEST.pdf | 7 | 655,460 | 12,761 | 3,166 | 0.3191 | -272.1% |
| CLEITON DEST.pdf | 3 | 33,284 | 7,483 | 2,615 | 0.2048 | -232.0% |

## Tabela 2 — Consumo Consolidado por Produtor (2)

| Produtor | PDFs | Notas | Valor (R$) | Tok IN | Tok OUT | Custo (USD) | Eco % |
|---|--:|--:|--:|--:|--:|--:|--:|
| ADELA | 2 | 26 | 1,596,510 | 33,648 | 4,319 | 0.7151 | -331.5% |
| CLEITON | 1 | 3 | 33,284 | 7,476 | 2,615 | 0.2047 | -231.9% |

## Tabela 3 — Consumo por Agente

| Agent | Chamadas | Modelo predomin. | Tok IN | Tok OUT | Custo (USD) | %H | %S | %O |
|---|--:|---|--:|--:|--:|--:|--:|--:|
| A-00 | 5 | opus | 41,302 | 2,560 | 0.8115 | 0.0 | 0.0 | 100.0 |
| A-07 | 5 | sonnet | 4,938 | 2,606 | 0.0539 | 0.0 | 100.0 | 0.0 |
| A-08 | 5 | opus | 34,632 | 7,497 | 1.0818 | 0.0 | 0.0 | 100.0 |
| A-23 | 5 | sonnet | 4,310 | 2,481 | 0.0501 | 0.0 | 100.0 | 0.0 |
| A-27 | 5 | sonnet | 1,114 | 1,870 | 0.0314 | 0.0 | 100.0 | 0.0 |

## Tabela 4 — Mix de Modelos (alvo 80/15/5)

| Modelo | % chamadas | Custo (USD) |
|---|--:|--:|
| HAIKU | 0.0% | 0.0000 |
| SONNET | 60.0% | 0.1354 |
| OPUS | 40.0% | 1.8933 |

## Tabela 5 — Comparação com Ground-Truth (RESULTADOS_AUDITORIA.zip)

| Produtor | Tem GT? | PDF GT | Similaridade |
|---|---|---|--:|
| ADELA | ✅ | AUDITORIA_ADELA_2026.pdf | 0.70% |
| CLEITON | ✅ | AUDITORIA_CLEITON_2026.pdf | 0.60% |

**Similaridade média:** 0.65% (min 0.60%, max 0.70%)

## Projeção de Custo

| Cenário | Atual | Baseline (Sonnet) | Economia |
|---|--:|--:|--:|
| 5 análises | USD 2.0287 | USD 0.5141 | USD -1.5146 |
| 1.000 análises (projeção) | USD 405.7500 | USD 102.8200 | USD -302.9300 |

## Detalhes técnicos

- **Modo:** mock (estimativa via `len(prompt)//4` no prompt real)
- **Mix-alvo:** Haiku 80% · Sonnet 15% · Opus 5%
- **max_tokens:** calibrado por agente em `MAX_TOKENS_OTIMO`
- **Output ratio:** 40% do max_tokens (estimativa típica)
- **Prompt cache:** não simulado (modo conservador, custo real seria menor)
