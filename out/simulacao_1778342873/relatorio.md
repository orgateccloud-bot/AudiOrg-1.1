# Simulação NFE-Gado 2026 — Consumo de Tokens

**Pipeline:** `full` · **PDFs:** 3 · **Análises individuais:** 3 · **Análises consolidadas:** 2

## Resumo Executivo

| Métrica | Valor |
|---|--:|
| Custo total (mock) | USD 1.6471 |
| Baseline tudo-Sonnet | USD 6.8180 |
| **Economia absoluta** | USD 5.1709 |
| **Economia %** | **75.84%** |
| Mix de modelos (Haiku/Sonnet/Opus) | 78.6% / 17.9% / 3.6% |
| Total de chamadas Claude | 140 |
| PDFs vazios (sem extração) | 0 |

## Tabela 1 — Consumo por PDF Individual (3)

| PDF | Notas | Valor (R$) | Tok IN | Tok OUT | Custo (USD) | Economia % |
|---|--:|--:|--:|--:|--:|--:|
| ADELA REM.pdf | 19 | 941,050 | 59,432 | 16,505 | 0.4867 | 65.6% |
| ADELA DEST.pdf | 7 | 655,460 | 33,821 | 13,859 | 0.2730 | 79.6% |
| CLEITON DEST.pdf | 3 | 33,284 | 22,990 | 12,602 | 0.1817 | 86.1% |

## Tabela 2 — Consumo Consolidado por Produtor (2)

| Produtor | PDFs | Notas | Valor (R$) | Tok IN | Tok OUT | Custo (USD) | Eco % |
|---|--:|--:|--:|--:|--:|--:|--:|
| ADELA | 2 | 26 | 1,596,510 | 70,989 | 16,870 | 0.5239 | 63.9% |
| CLEITON | 1 | 3 | 33,284 | 22,940 | 12,600 | 0.1817 | 86.1% |

## Tabela 3 — Consumo por Agente

| Agent | Chamadas | Modelo predomin. | Tok IN | Tok OUT | Custo (USD) | %H | %S | %O |
|---|--:|---|--:|--:|--:|--:|--:|--:|
| A-00 | 5 | sonnet | 38,092 | 2,560 | 0.1527 | 0.0 | 100.0 | 0.0 |
| A-01 | 5 | haiku | 1,442 | 1,670 | 0.0078 | 100.0 | 0.0 | 0.0 |
| A-02 | 5 | haiku | 2,391 | 1,905 | 0.0095 | 100.0 | 0.0 | 0.0 |
| A-03 | 5 | haiku | 4,884 | 2,396 | 0.0135 | 100.0 | 0.0 | 0.0 |
| A-04 | 5 | haiku | 1,667 | 1,870 | 0.0088 | 100.0 | 0.0 | 0.0 |
| A-05 | 5 | haiku | 585 | 1,870 | 0.0080 | 100.0 | 0.0 | 0.0 |
| A-06 | 5 | haiku | 155 | 1,870 | 0.0076 | 100.0 | 0.0 | 0.0 |
| A-07 | 5 | sonnet | 4,936 | 2,160 | 0.0472 | 0.0 | 100.0 | 0.0 |
| A-08 | 5 | opus | 31,502 | 7,365 | 1.0249 | 0.0 | 0.0 | 100.0 |
| A-09 | 5 | haiku | 4,740 | 2,400 | 0.0134 | 100.0 | 0.0 | 0.0 |
| A-10 | 5 | haiku | 4,735 | 2,390 | 0.0134 | 100.0 | 0.0 | 0.0 |
| A-11 | 5 | haiku | 2,065 | 1,870 | 0.0091 | 100.0 | 0.0 | 0.0 |
| A-12 | 5 | haiku | 4,575 | 2,390 | 0.0132 | 100.0 | 0.0 | 0.0 |
| A-13 | 5 | haiku | 4,465 | 2,310 | 0.0128 | 100.0 | 0.0 | 0.0 |
| A-14 | 5 | haiku | 4,765 | 2,400 | 0.0134 | 100.0 | 0.0 | 0.0 |
| A-15 | 5 | sonnet | 4,820 | 2,400 | 0.0273 | 0.0 | 100.0 | 0.0 |
| A-16 | 5 | haiku | 4,605 | 2,390 | 0.0132 | 100.0 | 0.0 | 0.0 |
| A-17 | 5 | haiku | 1,570 | 1,870 | 0.0087 | 100.0 | 0.0 | 0.0 |
| A-18 | 5 | haiku | 7,020 | 2,801 | 0.0168 | 100.0 | 0.0 | 0.0 |
| A-19 | 5 | haiku | 31,446 | 7,650 | 0.0558 | 100.0 | 0.0 | 0.0 |
| A-20 | 5 | haiku | 1,737 | 1,870 | 0.0089 | 100.0 | 0.0 | 0.0 |
| A-21 | 5 | haiku | 2,589 | 1,960 | 0.0099 | 100.0 | 0.0 | 0.0 |
| A-22 | 5 | haiku | 1,324 | 1,870 | 0.0085 | 100.0 | 0.0 | 0.0 |
| A-23 | 5 | sonnet | 4,310 | 2,364 | 0.0484 | 0.0 | 100.0 | 0.0 |
| A-24 | 5 | haiku | 3,189 | 2,170 | 0.0112 | 100.0 | 0.0 | 0.0 |
| A-25 | 5 | haiku | 1,027 | 1,870 | 0.0083 | 100.0 | 0.0 | 0.0 |
| A-26 | 5 | haiku | 34,424 | 3,925 | 0.0432 | 100.0 | 0.0 | 0.0 |
| A-27 | 5 | sonnet | 1,112 | 1,870 | 0.0314 | 0.0 | 100.0 | 0.0 |

## Tabela 4 — Mix de Modelos (alvo 80/15/5)

| Modelo | % chamadas | Custo (USD) |
|---|--:|--:|
| HAIKU | 78.6% | 0.3152 |
| SONNET | 17.9% | 0.3070 |
| OPUS | 3.6% | 1.0249 |

## Tabela 5 — Comparação com Ground-Truth (RESULTADOS_AUDITORIA.zip)

| Produtor | Tem GT? | PDF GT | Similaridade |
|---|---|---|--:|
| ADELA | ✅ | AUDITORIA_ADELA_2026.pdf | 0.00% |
| CLEITON | ✅ | AUDITORIA_CLEITON_2026.pdf | 0.00% |

**Similaridade média:** 0.00% (min 0.00%, max 0.00%)

## Projeção de Custo

| Cenário | Atual | Baseline (Sonnet) | Economia |
|---|--:|--:|--:|
| 5 análises | USD 1.6471 | USD 6.8180 | USD 5.1709 |
| 1.000 análises (projeção) | USD 329.4200 | USD 1,363.6000 | USD 1,034.1800 |

## Detalhes técnicos

- **Modo:** mock (estimativa via `len(prompt)//4` no prompt real)
- **Mix-alvo:** Haiku 80% · Sonnet 15% · Opus 5%
- **max_tokens:** calibrado por agente em `MAX_TOKENS_OTIMO`
- **Output ratio:** 40% do max_tokens (estimativa típica)
- **Prompt cache:** não simulado (modo conservador, custo real seria menor)
