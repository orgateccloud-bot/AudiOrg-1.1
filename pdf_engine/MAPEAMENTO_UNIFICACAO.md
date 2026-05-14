# Mapeamento da Unificação do `pdf_engine/`

> **Data:** 2026-05-13  
> **Versão consolidada:** OrgAudi 2.5.0

## Sumário Executivo

Antes da unificação existiam **3 versões coexistindo** com duplicações, imports quebrados e arquivos órfãos. Após a unificação:

- ✅ **1 pasta única** (`pdf_engine/orgaudi/`) com todo o motor
- ✅ **API pública limpa** via `pdf_engine/__init__.py`
- ✅ **Versões antigas arquivadas** em `pdf_engine/_legacy/`
- ✅ **0 imports quebrados**, sem duplicação

## Estrutura Antes vs Depois

### Antes (caótico)
```
pdf_engine/
├── __init__.py              (vazio)
├── pdf_report.py            (órfão, ReportLab manual)
├── ir_report.py             (órfão, planilha IR)
├── excel_export.py          (auxiliar)
├── orgaudi_v240/            (modular ReportLab — 13 arquivos)
├── orgaudi_v250/            (HTML/Chrome — 4 arquivos, importa de v240)
└── orgaudi_v4/              (MONOLÍTICO 3.360 linhas — duplica tudo)
    ├── orgaudi_v4.py
    ├── orgaudi_adapter.py
    └── orgaudi_tipologias.py
```

### Depois (unificado)
```
pdf_engine/
├── __init__.py              ⭐ API pública (re-exporta tudo de orgaudi/)
├── excel_export.py          (auxiliar — mantido na raiz)
├── orgaudi/                 ⭐ MOTOR UNIFICADO
│   ├── __init__.py          (exports + docstring completa)
│   ├── __main__.py          (entry: python -m pdf_engine.orgaudi)
│   ├── domain.py            (dataclasses + enums)
│   ├── validators.py        (CPF/CNPJ + formatadores)
│   ├── data_processing.py   (F1-F6, testes T-01/02/04/07)
│   ├── catalog.py           (18 tipologias × 5 eixos)
│   ├── styles.py            (paleta + componentes ReportLab)
│   ├── handlers.py          (header/footer canvas)
│   ├── pages.py             (8 páginas do laudo)
│   ├── report_builder.py    ⭐ v2.5 HTML/Chrome (PADRÃO)
│   ├── report_builder_rl.py    v2.4 ReportLab (alternativa)
│   ├── template_builder.py  (HTML self-contained)
│   ├── renderer.py          (Chrome headless → PDF)
│   ├── adapter.py           (nfa-repo.NFA → NotaFiscal)
│   └── cli.py               (3 modos: interativo/rápido/batch)
└── _legacy/                 (arquivado — só para referência histórica)
    ├── orgaudi_v240/
    ├── orgaudi_v250/
    ├── orgaudi_v4/          (3.360 linhas duplicadas — agora isolado)
    ├── pdf_report.py
    └── ir_report.py
```

## Tabela de Migração

| Arquivo Original | Destino | Notas |
|---|---|---|
| `orgaudi_v240/domain.py` | `orgaudi/domain.py` | Inalterado |
| `orgaudi_v240/validators.py` | `orgaudi/validators.py` | Inalterado |
| `orgaudi_v240/data_processing.py` | `orgaudi/data_processing.py` | Inalterado |
| `orgaudi_v240/catalog.py` | `orgaudi/catalog.py` | Inalterado |
| `orgaudi_v240/styles.py` | `orgaudi/styles.py` | Inalterado |
| `orgaudi_v240/handlers.py` | `orgaudi/handlers.py` | Inalterado |
| `orgaudi_v240/pages.py` | `orgaudi/pages.py` | Imports `..X` → `.X` (corrigidos) |
| `orgaudi_v240/report_builder.py` | `orgaudi/report_builder_rl.py` | **Renomeado** para não conflitar com v250 |
| `orgaudi_v240/cli.py` | `orgaudi/cli.py` | Import `.report_builder` → `.report_builder_rl` |
| `orgaudi_v250/report_builder.py` | `orgaudi/report_builder.py` | **PADRÃO**; imports `..orgaudi_v240` → `.` |
| `orgaudi_v250/template_builder.py` | `orgaudi/template_builder.py` | Inalterado |
| `orgaudi_v250/renderer.py` | `orgaudi/renderer.py` | Inalterado |
| `orgaudi_v4/orgaudi_adapter.py` | `orgaudi/adapter.py` | **Renomeado**; imports `..orgaudi_v240` → `.domain` |
| `orgaudi_v4/orgaudi_v4.py` | `_legacy/` | **Descartado** — 3.360 linhas duplicadas |
| `orgaudi_v4/orgaudi_tipologias.py` | `_legacy/` | **Descartado** — duplica `catalog.py` |
| `pdf_report.py` | `_legacy/` | Órfão, nunca importado |
| `ir_report.py` | `_legacy/` | Órfão, nunca importado |
| `excel_export.py` | (mantido na raiz) | Auxiliar, não é PDF |

## Erros Corrigidos

### Imports relativos quebrados
| Arquivo | Antes | Depois |
|---|---|---|
| `orgaudi/pages.py` L51 | `from ..data_processing import` | `from .data_processing import` |
| `orgaudi/pages.py` L56 | `from ..domain import` | `from .domain import` |
| `orgaudi/pages.py` L64 | `from ..styles import` | `from .styles import` |
| `orgaudi/pages.py` L93 | `from ..validators import` | `from .validators import` |
| `orgaudi/report_builder.py` L25 | `from ..orgaudi_v240.data_processing import` | `from .data_processing import` |
| `orgaudi/report_builder.py` L34 | `from ..orgaudi_v240.domain import` | `from .domain import` |
| `orgaudi/report_builder.py` L42 | `from ..orgaudi_v240.validators import` | `from .validators import` |
| `orgaudi/report_builder.py` L171 | `from ..orgaudi_v240.report_builder import LaudoOrgAudi` | `from .report_builder_rl import LaudoOrgAudi` |
| `orgaudi/adapter.py` L30 | `from ..orgaudi_v240 import` | `from .domain import` |
| `orgaudi/cli.py` L33 | `from .report_builder import` | `from .report_builder_rl import` |

### Arquivos órfãos eliminados
- `pdf_report.py` (356 linhas) → `_legacy/`
- `ir_report.py` (452 linhas) → `_legacy/`
- `orgaudi_v4/orgaudi_v4.py` (3.360 linhas duplicadas) → `_legacy/`
- `orgaudi_v4/orgaudi_tipologias.py` (253 linhas duplicadas) → `_legacy/`

**Total eliminado:** ~4.421 linhas de código duplicado/órfão.

## Nova API Pública

```python
# Forma recomendada (motor v2.5 HTML/Chrome)
from pdf_engine import gerar_laudo_v250

gerar_laudo_v250(notas, "Nome", "CPF11", Path("saida.pdf"), municipio="Formoso", estado="GO")

# Alias semântico
from pdf_engine import gerar_laudo
gerar_laudo(notas, ...)

# Adapter para nfa-repo (converte NFA → NotaFiscal)
from pdf_engine import gerar_laudo_orgaudi
gerar_laudo_orgaudi(notas_nfa, "Nome", "CPF11", Path("saida.pdf"))

# Alternativa ReportLab puro (v2.4)
from pdf_engine import LaudoOrgAudi
laudo = LaudoOrgAudi(contribuinte, periodo, notas)
laudo.processar()
laudo.gerar_pdf("saida.pdf")

# Dataclasses (tipo único — não duplicado mais)
from pdf_engine import (
    Achado, Contribuinte, NotaFiscal, Periodo,
    Severidade, NaturezaNota, CategoriaContabil,
)
```

## Verificação

```bash
# 1. Imports funcionam:
python -c "from pdf_engine import gerar_laudo_v250; print('OK')"

# 2. CLI funciona:
python -m pdf_engine.orgaudi --help

# 3. Geração de PDFs:
python scripts/gerar_pdfs_individuais.py
```

## Recomendações

1. **Após validar em produção** (1-2 semanas): remover `_legacy/` por completo
2. **Migrar imports antigos** em outros módulos do projeto:
   - `from pdf_engine.orgaudi_v240.X` → `from pdf_engine.X`
   - `from pdf_engine.orgaudi_v250.report_builder` → `from pdf_engine`
   - `from pdf_engine.orgaudi_v4.orgaudi_adapter` → `from pdf_engine import gerar_laudo_orgaudi`
3. **Documentar** em `pdf_engine/orgaudi/__init__.py` os endpoints públicos (já feito)
4. **Considerar** mover `excel_export.py` para um pacote separado `pdf_engine/export/`
