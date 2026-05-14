# Simulação NFE-Gado 2026 — Consumo de Tokens

**Pipeline:** `full` · **PDFs:** 3 · **Análises individuais:** 3 · **Análises consolidadas:** 2

## Resumo Executivo

| Métrica | Valor |
|---|--:|
| Custo total (mock) | USD 3.1942 |
| Baseline tudo-Sonnet | USD 7.0297 |
| **Economia absoluta** | USD 3.8354 |
| **Economia %** | **54.56%** |
| Mix de modelos (Haiku/Sonnet/Opus) | 78.6% / 14.3% / 7.1% |
| Total de chamadas Claude | 140 |
| PDFs vazios (sem extração) | 0 |

## Tabela 1 — Consumo por PDF Individual (3)

| PDF | Notas | Valor (R$) | Tok IN | Tok OUT | Custo (USD) | Economia % |
|---|--:|--:|--:|--:|--:|--:|
| ADELA REM.pdf | 19 | 941,050 | 74,785 | 17,636 | 0.8582 | 41.3% |
| ADELA DEST.pdf | 7 | 655,460 | 46,179 | 15,032 | 0.5302 | 61.5% |
| CLEITON DEST.pdf | 3 | 33,284 | 34,074 | 13,776 | 0.3898 | 70.9% |

## Tabela 2 — Consumo Consolidado por Produtor (2)

| Produtor | PDFs | Notas | Valor (R$) | Tok IN | Tok OUT | Custo (USD) | Eco % |
|---|--:|--:|--:|--:|--:|--:|--:|
| ADELA | 2 | 26 | 1,596,510 | 91,657 | 18,001 | 1.0265 | 32.1% |
| CLEITON | 1 | 3 | 33,284 | 34,022 | 13,768 | 0.3896 | 70.9% |

## Tabela 3 — Consumo por Agente

| Agent | Chamadas | Modelo predomin. | Tok IN | Tok OUT | Custo (USD) | %H | %S | %O |
|---|--:|---|--:|--:|--:|--:|--:|--:|
| A-00 | 5 | opus | 94,069 | 2,560 | 1.6030 | 0.0 | 0.0 | 100.0 |
| A-01 | 5 | haiku | 1,442 | 1,670 | 0.0078 | 100.0 | 0.0 | 0.0 |
| A-02 | 5 | haiku | 2,392 | 2,096 | 0.0103 | 100.0 | 0.0 | 0.0 |
| A-03 | 5 | haiku | 4,886 | 2,596 | 0.0143 | 100.0 | 0.0 | 0.0 |
| A-04 | 5 | haiku | 1,670 | 1,950 | 0.0091 | 100.0 | 0.0 | 0.0 |
| A-05 | 5 | haiku | 580 | 1,870 | 0.0079 | 100.0 | 0.0 | 0.0 |
| A-06 | 5 | haiku | 150 | 1,870 | 0.0076 | 100.0 | 0.0 | 0.0 |
| A-07 | 5 | sonnet | 4,938 | 2,606 | 0.0539 | 0.0 | 100.0 | 0.0 |
| A-08 | 5 | opus | 34,632 | 7,497 | 1.0818 | 0.0 | 0.0 | 100.0 |
| A-09 | 5 | haiku | 4,740 | 2,565 | 0.0140 | 100.0 | 0.0 | 0.0 |
| A-10 | 5 | haiku | 4,740 | 2,565 | 0.0140 | 100.0 | 0.0 | 0.0 |
| A-11 | 5 | haiku | 2,066 | 2,032 | 0.0098 | 100.0 | 0.0 | 0.0 |
| A-12 | 5 | haiku | 4,580 | 2,535 | 0.0138 | 100.0 | 0.0 | 0.0 |
| A-13 | 5 | haiku | 8,830 | 3,385 | 0.0206 | 100.0 | 0.0 | 0.0 |
| A-14 | 5 | haiku | 4,770 | 2,570 | 0.0141 | 100.0 | 0.0 | 0.0 |
| A-15 | 5 | sonnet | 4,820 | 2,580 | 0.0300 | 0.0 | 100.0 | 0.0 |
| A-16 | 5 | haiku | 4,610 | 2,540 | 0.0138 | 100.0 | 0.0 | 0.0 |
| A-17 | 5 | haiku | 1,570 | 1,930 | 0.0090 | 100.0 | 0.0 | 0.0 |
| A-18 | 5 | haiku | 14,056 | 4,429 | 0.0290 | 100.0 | 0.0 | 0.0 |
| A-19 | 5 | haiku | 31,446 | 7,908 | 0.0568 | 100.0 | 0.0 | 0.0 |
| A-20 | 5 | haiku | 1,740 | 1,966 | 0.0093 | 100.0 | 0.0 | 0.0 |
| A-21 | 5 | haiku | 2,594 | 2,136 | 0.0106 | 100.0 | 0.0 | 0.0 |
| A-22 | 5 | haiku | 1,326 | 1,883 | 0.0086 | 100.0 | 0.0 | 0.0 |
| A-23 | 5 | sonnet | 4,310 | 2,481 | 0.0501 | 0.0 | 100.0 | 0.0 |
| A-24 | 5 | haiku | 3,190 | 2,256 | 0.0116 | 100.0 | 0.0 | 0.0 |
| A-25 | 5 | haiku | 1,032 | 1,870 | 0.0083 | 100.0 | 0.0 | 0.0 |
| A-26 | 5 | haiku | 34,424 | 3,997 | 0.0435 | 100.0 | 0.0 | 0.0 |
| A-27 | 5 | sonnet | 1,114 | 1,870 | 0.0314 | 0.0 | 100.0 | 0.0 |

## Tabela 4 — Mix de Modelos (alvo 80/15/5)

| Modelo | % chamadas | Custo (USD) |
|---|--:|--:|
| HAIKU | 78.6% | 0.3439 |
| SONNET | 14.3% | 0.1655 |
| OPUS | 7.1% | 2.6848 |

## Tabela 5 — Comparação com Ground-Truth (RESULTADOS_AUDITORIA.zip)

| Produtor | Tem GT? | PDF GT | Similaridade |
|---|---|---|--:|
| ADELA | ✅ | AUDITORIA_ADELA_2026.pdf | 0.00% |
| CLEITON | ✅ | AUDITORIA_CLEITON_2026.pdf | 0.00% |

**Similaridade média:** 0.00% (min 0.00%, max 0.00%)

## Projeção de Custo

| Cenário | Atual | Baseline (Sonnet) | Economia |
|---|--:|--:|--:|
| 5 análises | USD 3.1942 | USD 7.0297 | USD 3.8354 |
| 1.000 análises (projeção) | USD 638.8400 | USD 1,405.9300 | USD 767.0900 |

## Detalhes técnicos

- **Modo:** mock (estimativa via `len(prompt)//4` no prompt real)
- **Mix-alvo:** Haiku 80% · Sonnet 15% · Opus 5%
- **max_tokens:** calibrado por agente em `MAX_TOKENS_OTIMO`
- **Output ratio:** 40% do max_tokens (estimativa típica)
- **Prompt cache:** não simulado (modo conservador, custo real seria menor)
