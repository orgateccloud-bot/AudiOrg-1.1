# Reconfiguração de Mix — 80/15/5 (rev 2026-05-09)

## Política aprovada

| Tier | Alvo | Real | Quando usar |
|---|---:|---:|---|
| **Haiku** | 80% | **78,6%** (22 agentes) | Toda operação de baixa/média complexidade |
| **Sonnet** | 15% | **14,3%** (4 agentes) | Raciocínio cruzado entre agentes (assurance, anomalias, grafo, jurídico) |
| **Opus** | 5% | **7,1%** (2 agentes) | Exclusivo: **AUDITORIA** (A-08) e **DECISÃO FINAL** (A-00) |

## Distribuição final

### 🟢 HAIKU (22 agentes — 78,6%)
| Agent | Função | Tipo |
|---|---|---|
| A-01 | @Junior — roteador | ROTEAMENTO |
| A-02 | @Protetor — guarda | CONFORMIDADE |
| A-03 | @ZeroTrust — integridade | CONFORMIDADE |
| A-04 | @Vigilante — monitoramento | CONFORMIDADE |
| A-05 | @Engenheiro-ERP | EXTRACAO |
| A-06 | @Extrator-Faturas | EXTRACAO |
| A-09 | @Auditor-TI | CONFORMIDADE |
| A-10 | @Auditor-Patrimonio | PATRIMONIO |
| A-11 | @Planejador-Tributario | PLANEJAMENTO |
| A-12 | @Descobridor-Deducoes | PLANEJAMENTO |
| A-13 | @Monitor-Conformidade | CONFORMIDADE |
| A-14 | @Avaliador-Risco | CLASSIFICACAO |
| A-16 | @LGPD | LGPD |
| A-17 | @Previsor-Caixa | PLANEJAMENTO |
| A-18 | @Analista-CSuite | CLASSIFICACAO |
| A-19 | @Contabilista-IA | PATRIMONIO |
| A-20 | @Esocial-IA | ESOCIAL |
| A-21 | @Auditor-ICMS | ICMS |
| A-22 | @Auditor-ITR | ITR |
| A-24 | @Classificador-CFOP | CLASSIFICACAO |
| A-25 | @Auditor-LCDPR | LCDPR |
| A-26 | @Auditor-Biologicos | PATRIMONIO |

### 🟡 SONNET (4 agentes — 14,3%)
| Agent | Função | Razão |
|---|---|---|
| A-07 | @Auditoria-Assurance | Entrada do funil — score híbrido |
| A-15 | @Juridico-Ext | Pareceres jurídicos exigem nuance |
| A-23 | @Analista-Anomalias | Cruzamento AN-01..AN-18 + SHAP |
| A-27 | @Epsilon-Forensic | Grafo de conluio |

### 🔴 OPUS (2 agentes — 7,1%)
| Agent | Função | Razão |
|---|---|---|
| A-08 | @Auditor-NFA | Auditoria fiscal rural com Schema rígido (14 campos) |
| A-00 | @CEO | Decisão final agregando todos os agentes |

## Escalada condicional (Sonnet → Opus)

Apenas os **4 agentes Sonnet** podem subir para Opus quando:
- `score_risco ≥ 85` ou
- `tipologias_criticas ≥ 3` ou
- `probabilidade_autuacao ≥ 75%`

Os **22 Haiku permanecem Haiku** mesmo em cenário crítico — quem decide caso crítico no fim é o A-08 (Opus base) e A-00 (Opus base).

## Custo por execução completa (28 agentes, ~3500 tokens in / 800 out cada)

| Cenário | Haiku | Sonnet | Opus | **Custo total** | vs tudo-Sonnet |
|---|---:|---:|---:|---:|---|
| **Baseline** (score=42) | 22 | 4 | 2 | **USD 0,447** | **−29%** ↓ |
| **Alerta** (score=70) | 22 | 4 | 2 | **USD 0,447** | **−29%** ↓ |
| **Crítico** (score=90, 4 tipologias) | 22 | 0 | **6** ⬆ | **USD 0,807** | +28% ↑ |

**Em produção típica (95% baseline + 5% crítico):** custo médio = **USD 0,465 / auditoria** vs USD 0,630 com tudo-Sonnet → **economia de 26%**.

## Antes vs Depois

| Métrica | Antes (rev anterior) | Depois (80/15/5) |
|---|---:|---:|
| Haiku | 5 (21%) | **22 (79%)** |
| Sonnet | 17 (71%) | **4 (14%)** |
| Opus | 2 (8%) | **2 (7%)** |
| Custo baseline | USD 0,615 | **USD 0,447** (−27%) |
| Risco de explosão Opus | 28 agentes (custo +400%) | **6 agentes** (+28% controlado) |

## Arquivos modificados
- [horizon_blue_one/core/token_router.py](horizon_blue_one/core/token_router.py) — `_MODELO_BASE` + `_AGENTE_TAREFA` + regra de escalada Sonnet-only
- [scripts/simulacao_mix_modelos.py](scripts/simulacao_mix_modelos.py) — script de validação com 3 cenários

## Como aplicar nos demais agentes

Os 22 agentes Haiku ainda chamam `call_model(ModelType.SONNET, ...)` direto.
Para colher a economia, substituir por:
```python
from horizon_blue_one.agents.a_token import call_otimizado
from horizon_blue_one.core.token_router import TipoTarefa

resp, decision = await call_otimizado(
    prompt, SYSTEM,
    tipo_tarefa=TipoTarefa.<a definir>,
    score_risco=score_atual,
    agent_id=self.agent_id,   # router faz lookup automático no _AGENTE_TAREFA
)
```

A-23 e A-27 já estão migrados como referência.
