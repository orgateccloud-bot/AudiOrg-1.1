# Simulação NFE-Gado 2026 — Consumo de Tokens

**Pipeline:** `full` · **PDFs:** 3 · **Análises individuais:** 3 · **Análises consolidadas:** 2

## Resumo Executivo

| Métrica | Valor |
|---|--:|
| Custo total (mock) | USD 0.6777 |
| Baseline tudo-Sonnet | USD 6.1815 |
| **Economia absoluta** | USD 5.5038 |
| **Economia %** | **89.04%** |
| Mix de modelos (Haiku/Sonnet/Opus) | 76.9% / 23.1% / 0.0% |
| Total de chamadas Claude | 130 |
| PDFs vazios (sem extração) | 0 |

## Tabela 1 — Consumo por PDF Individual (3)

| PDF | Notas | Valor (R$) | Tok IN | Tok OUT | Custo (USD) | Economia % |
|---|--:|--:|--:|--:|--:|--:|
| ADELA REM.pdf | 19 | 941,050 | 39,115 | 13,509 | 0.1641 | 87.0% |
| ADELA DEST.pdf | 7 | 655,460 | 24,812 | 12,113 | 0.1241 | 89.8% |
| CLEITON DEST.pdf | 3 | 33,284 | 18,354 | 11,219 | 0.1015 | 91.6% |

## Tabela 2 — Consumo Consolidado por Produtor (2)

| Produtor | PDFs | Notas | Valor (R$) | Tok IN | Tok OUT | Custo (USD) | Eco % |
|---|--:|--:|--:|--:|--:|--:|--:|
| ADELA | 2 | 26 | 1,596,510 | 47,404 | 13,849 | 0.1866 | 85.5% |
| CLEITON | 1 | 3 | 33,284 | 18,309 | 11,217 | 0.1014 | 91.6% |

## Tabela 3 — Consumo por Agente

| Agent | Chamadas | Modelo predomin. | Tok IN | Tok OUT | Custo (USD) | %H | %S | %O |
|---|--:|---|--:|--:|--:|--:|--:|--:|
| A-00 | 5 | sonnet | 27,654 | 2,560 | 0.1214 | 0.0 | 100.0 | 0.0 |
| A-01 | 5 | haiku | 1,442 | 1,670 | 0.0078 | 100.0 | 0.0 | 0.0 |
| A-02 | 5 | haiku | 2,391 | 1,905 | 0.0095 | 100.0 | 0.0 | 0.0 |
| A-03 | 5 | haiku | 6,368 | 2,693 | 0.0159 | 100.0 | 0.0 | 0.0 |
| A-04 | 5 | haiku | 1,649 | 1,870 | 0.0088 | 100.0 | 0.0 | 0.0 |
| A-05 | 5 | haiku | 585 | 1,870 | 0.0080 | 100.0 | 0.0 | 0.0 |
| A-06 | 5 | haiku | 155 | 1,870 | 0.0076 | 100.0 | 0.0 | 0.0 |
| A-07 | 5 | sonnet | 4,511 | 2,074 | 0.0446 | 0.0 | 100.0 | 0.0 |
| A-08 | 5 | sonnet | 28,454 | 5,040 | 0.1610 | 0.0 | 100.0 | 0.0 |
| A-10 | 5 | haiku | 4,735 | 2,390 | 0.0134 | 100.0 | 0.0 | 0.0 |
| A-11 | 5 | haiku | 2,065 | 1,870 | 0.0091 | 100.0 | 0.0 | 0.0 |
| A-12 | 5 | haiku | 4,575 | 2,390 | 0.0132 | 100.0 | 0.0 | 0.0 |
| A-13 | 5 | haiku | 4,185 | 2,255 | 0.0124 | 100.0 | 0.0 | 0.0 |
| A-14 | 5 | haiku | 4,765 | 2,400 | 0.0134 | 100.0 | 0.0 | 0.0 |
| A-15 | 5 | sonnet | 4,820 | 2,400 | 0.0273 | 0.0 | 100.0 | 0.0 |
| A-16 | 5 | haiku | 4,605 | 2,390 | 0.0132 | 100.0 | 0.0 | 0.0 |
| A-17 | 5 | haiku | 1,570 | 1,870 | 0.0087 | 100.0 | 0.0 | 0.0 |
| A-18 | 5 | haiku | 6,688 | 2,735 | 0.0163 | 100.0 | 0.0 | 0.0 |
| A-19 | 5 | haiku | 22,294 | 5,819 | 0.0411 | 100.0 | 0.0 | 0.0 |
| A-20 | 5 | haiku | 1,737 | 1,870 | 0.0089 | 100.0 | 0.0 | 0.0 |
| A-21 | 5 | haiku | 2,434 | 1,937 | 0.0097 | 100.0 | 0.0 | 0.0 |
| A-22 | 5 | haiku | 1,309 | 1,870 | 0.0085 | 100.0 | 0.0 | 0.0 |
| A-23 | 5 | sonnet | 4,200 | 2,340 | 0.0477 | 0.0 | 100.0 | 0.0 |
| A-24 | 5 | haiku | 2,676 | 2,079 | 0.0105 | 100.0 | 0.0 | 0.0 |
| A-25 | 5 | haiku | 1,015 | 1,870 | 0.0083 | 100.0 | 0.0 | 0.0 |
| A-27 | 5 | sonnet | 1,112 | 1,870 | 0.0314 | 0.0 | 100.0 | 0.0 |

## Tabela 4 — Mix de Modelos (alvo 80/15/5)

| Modelo | % chamadas | Custo (USD) |
|---|--:|--:|
| HAIKU | 76.9% | 0.2443 |
| SONNET | 23.1% | 0.4334 |
| OPUS | 0.0% | 0.0000 |

## Tabela 5 — Comparação com Ground-Truth (RESULTADOS_AUDITORIA.zip)

| Produtor | Tem GT? | PDF GT | Similaridade |
|---|---|---|--:|
| ADELA | ✅ | AUDITORIA_ADELA_2026.pdf | 0.00% |
| CLEITON | ✅ | AUDITORIA_CLEITON_2026.pdf | 0.00% |

**Similaridade média:** 0.00% (min 0.00%, max 0.00%)

## Projeção de Custo

| Cenário | Atual | Baseline (Sonnet) | Economia |
|---|--:|--:|--:|
| 5 análises | USD 0.6777 | USD 6.1815 | USD 5.5038 |
| 1.000 análises (projeção) | USD 135.5400 | USD 1,236.3000 | USD 1,100.7600 |

## Detalhes técnicos

- **Modo:** mock (estimativa via `len(prompt)//4` no prompt real)
- **Mix-alvo:** Haiku 80% · Sonnet 15% · Opus 5%
- **max_tokens:** calibrado por agente em `MAX_TOKENS_OTIMO`
- **Output ratio:** 40% do max_tokens (estimativa típica)
- **Prompt cache:** não simulado (modo conservador, custo real seria menor)
