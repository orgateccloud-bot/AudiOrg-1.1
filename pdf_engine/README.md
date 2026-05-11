# pdf_engine — Motor de Laudos PDF (OrgAudi)

Pacote responsável por transformar **notas fiscais avulsas (NFA-e)** em
**laudos PDF** prontos para entrega ao escritório contábil.

## Versões coexistentes

| Versão | Status | Motor | Quando usar |
|--------|--------|-------|-------------|
| `orgaudi_v4`   | Legado | ReportLab monolítico | Mantido só para `api/services/auditoria_bigfour.py:508`. Não usar em código novo. |
| `orgaudi_v240` | Suporte | ReportLab Platypus, 11 páginas | Provedor de dataclasses de domínio (`Contribuinte`, `NotaFiscal`, `Achado`) e pipeline de dados (`apurar_resumo`, `teste_t01..t07`). Consumido pelo v250. |
| `orgaudi_v250` | **Atual** | HTML+CSS + Chrome headless | **Use este.** Manrope + JetBrains Mono, capa editorial com gradiente navy/teal, KPIs, achados por severidade. |

## API pública (atalho v250)

```python
from pdf_engine import gerar_laudo_v250, gerar_laudo_sem_objeto_v250
from pathlib import Path

# Caso normal — produtor com NFA-e extraídas
gerar_laudo_v250(
    notas=lista_de_nfa,        # list[NFA] (nfa-repo) ou list[NotaFiscal]
    cliente_nome="GENIS",
    cliente_cpf="019.925.771-02",
    saida=Path("Laudo_GENIS.pdf"),
)

# Caso "sem objeto" — extrator retornou zero notas
gerar_laudo_sem_objeto_v250(
    cliente_nome="HELLIDA",
    cliente_cpf="024.979.491-82",
    saida=Path("Laudo_HELLIDA.pdf"),
)
```

**Detecção automática**: se você chamar `gerar_laudo_v250(notas=[], ...)`,
o pacote delega internamente para `gerar_laudo_sem_objeto_v250`. Nunca
mais retorna sem gerar PDF.

## Requisitos

- **Python 3.10+**
- **Google Chrome instalado** (Windows: caminho padrão; o `renderer.py`
  procura em `C:\Program Files\Google\Chrome\Application\chrome.exe` e
  variantes).
- **ReportLab** (apenas para v4/v240 — instalado via `requirements.txt`).

## Fontes

O `orgaudi_v250` espera as fontes **Manrope** e **JetBrains Mono** em
`pdf_engine/orgaudi_v250/assets/fonts/`. Se a pasta estiver vazia, o
Chrome cai em fallback (Segoe UI / Consolas no Windows) e o pacote loga
um único `DEBUG` agregado — sem flood de warnings.

Para fidelidade total ao design, baixar:
- Manrope 300/400/500/600/700/800 → `manrope-{peso}.ttf`
- JetBrains Mono 400/500/700 → `jetbrains-{peso}.ttf`

## Estrutura

```
pdf_engine/
├── __init__.py                 # API pública: gerar_laudo_v250, gerar_laudo_sem_objeto_v250
├── orgaudi_v250/               # Motor atual (HTML+CSS+Chrome)
│   ├── report_builder.py       # Pipeline NFA → ctx → HTML → PDF
│   ├── template_builder.py     # HTML + CSS embutidos
│   ├── renderer.py             # Chrome headless --print-to-pdf
│   ├── sem_objeto.py           # Variante "auditoria sem objeto"
│   └── assets/fonts/           # Manrope + JetBrains Mono (opcional)
├── orgaudi_v240/               # Camada de domínio + ReportLab v2.4
│   ├── domain.py               # NotaFiscal, Contribuinte, Achado, Severidade
│   ├── data_processing.py      # Testes T-01..T-07, apurar_resumo, hash_laudo
│   └── ...
├── orgaudi_v4/                 # LEGADO — não usar em código novo
│   └── orgaudi_adapter.py      # NFA (nfa-repo) → NotaFiscal (v240)
├── pdf_report.py               # LEGADO ReportLab (depende de nfa_extractor)
├── ir_report.py                # LEGADO IR
└── excel_export.py             # Export Excel
```

## Consumidores no projeto

| Caller | Versão | Como importa |
|--------|--------|--------------|
| `scripts/auditar_lote_completo_pdf.py` | v250 | `from pdf_engine.orgaudi_v250.report_builder import gerar_laudo_v250` |
| `scripts/gerar_laudo_sem_objeto.py`    | v250 | `from pdf_engine import gerar_laudo_sem_objeto_v250` |
| `api/services/auditoria_bigfour.py:508` | v4 | `from pdf_engine.orgaudi_v4.orgaudi_adapter import gerar_laudo_orgaudi` |

## Roadmap

- [ ] Migrar `api/services/auditoria_bigfour.py` de v4 para v250.
- [ ] Adicionar as 9 fontes (Manrope/JetBrains) ao repositório ou via download script.
- [ ] Deletar `pdf_report.py` e `ir_report.py` legacy depois de confirmar
      que nenhum consumidor ainda usa.
