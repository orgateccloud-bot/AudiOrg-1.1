# Catálogo de Agentes — OrgAudi v8.0.0

## Agentes em Produção

| ID | Nome | Módulo | Status | Função |
|--|--|--|--|--|
| **A-07** | Auditoria Assurance | `a07_auditoria_assurance.py` | ✅ ATIVO | 5 detectores forenses (CARROSSEL, SMURFING, etc.) |
| **A-08** | Auditor NFA-e | `a08_auditor_nfa.py` | ✅ ATIVO | Análise qualitativa via LLM + fallback determinístico |

**Pipeline Padrão:**
```
POST /nfae
  ├─ RE-1 (regra_especial_1.py) — reclassificação VENDA→COMPRA
  ├─ XGBoost (xgboost_scorer.py) — score 0-100
  ├─ F1-F6 (resumo_fiscal.py) — apuração FUNRURAL
  ├─ A-07 (a07_...) — detectores forenses ← AQUI
  └─ A-08 (a08_...) — análise LLM ← AQUI
```

---

## Agentes em Protótipo (Não-Integrados)

| ID | Nome | Status | Propósito |
|--|--|--|--|
| a00 | CEO | 🟡 EXPERIMENTAL | Orquestrador estratégico |
| a01 | Junior | 🟡 EXPERIMENTAL | Assistente júnior |
| a02 | Protetor | 🟡 EXPERIMENTAL | Identificação de riscos |
| a03 | Zero Trust | 🟡 EXPERIMENTAL | Auditoria de segurança |
| a04 | Vigilante | 🟡 EXPERIMENTAL | Monitoramento contínuo |
| a05 | Engenheiro ERP | 🟡 EXPERIMENTAL | Integração SAP/Oracle |
| a06 | Extrator | 🟡 EXPERIMENTAL | Parser de documentos |
| a09 | Auditor TI | 🟡 EXPERIMENTAL | Auditoria de infraestrutura |
| a10 | Auditor Patrimônio | 🟡 EXPERIMENTAL | Imobilizado e ativos |
| a11 | Planejador Tributário | 🟡 EXPERIMENTAL | Otimização fiscal |
| a12 | Descobridor Deduções | 🟡 EXPERIMENTAL | Identificação de créditos |
| a13 | Monitor Conformidade | 🟡 EXPERIMENTAL | Compliance contínuo |
| a14 | Avaliador Risco | 🟡 EXPERIMENTAL | Tipologia de risco |
| a15 | Jurídico EXT | 🟡 EXPERIMENTAL | Análise legal |
| a16 | LGPD | 🟡 EXPERIMENTAL | Conformidade dados |
| a17 | Previsor Caixa | 🟡 EXPERIMENTAL | Projeção de fluxo |
| a18 | Analista C-Suite | 🟡 EXPERIMENTAL | Executivo-friendly reports |
| a19 | Contabilista IA | 🟡 EXPERIMENTAL | Lançamentos contábeis |
| a20 | eSocial IA | 🟡 EXPERIMENTAL | Folha e SEFIP |
| a21 | Auditor ICMS | 🟡 EXPERIMENTAL | Impostos estaduais |
| a22 | Auditor ITR | 🟡 EXPERIMENTAL | Imposto territorial rural |
| a23 | Analista Anomalias | 🟡 EXPERIMENTAL | Detecção de outliers |
| a24 | Classificador CFOP | 🟡 EXPERIMENTAL | CFOP correto automático |
| a25 | Auditor LCDPR | 🟡 EXPERIMENTAL | Lei da Cadeia de Custódia |
| a26 | Auditor Biológicos | 🟡 EXPERIMENTAL | Pecuária especializada |
| a27 | Epsilon Forensic | 🟡 EXPERIMENTAL | Análise forense avançada |

**Status:** 26 agentes em standby, sem testes ou integração ao pipeline.

---

## Recomendações

### Imediatas (Próximas 2 semanas)
1. **Documentar intenção** dos 26 agentes:
   - Agendar para produção? (timeline)
   - Arquivar temporariamente?
   - Remover completamente?

2. **Cleanup inicial**: Mover agentes não-viáveis para `_archived/`
   ```bash
   mkdir horizon_blue_one/agents/_archived
   git mv horizon_blue_one/agents/a{09..27}_*.py horizon_blue_one/agents/_archived/
   ```

### Médio prazo (1–3 meses)
- Integrar a05 (Engenheiro ERP) ao pipeline se recursos permitirem
- Testar a11 (Planejador Tributário) isoladamente
- Documenta use-cases para cada agente restante

### Longo prazo (6+ meses)
- Considerar sumarizar catálogo em squad (a00 = CEO, a01 = Admin, etc.)
- Implementar discovery dinâmico de agentes (registry pattern)

---

## Base Compartilhada

**`base_agent.py`**
```python
@dataclass
class AgentResult(BaseModel):
    status: str           # "OK", "ERRO", "PARCIAL"
    confidence: float     # 0.0–1.0
    audit_hash: str       # SHA-256 para rastreamento
    detalhes: Dict[str, Any]
    # Herdam todos os agentes
```

**Padrão de novo agente:**
```python
from horizon_blue_one.agents.base_agent import AgentResult

class MeuAgente:
    def processar(self, dados) -> AgentResult:
        # ... sua lógica ...
        return AgentResult(
            status="OK",
            confidence=0.95,
            audit_hash=sha256(str(dados).encode()).hexdigest(),
            detalhes={"resultado": ...}
        )
```

---

**Última atualização:** 2026-05-12  
**Próxima revisão:** 2026-06-12 (1 mês)
