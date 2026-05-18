# Clientes — Auditoria Cruzada OrgAudi 1.1

Cada arquivo `<slug>.json` neste diretório define os dados de **um cliente**
para gerar sua Auditoria Cruzada (JSON + DOCX + 2 PDFs + Markdown).

A arquitetura é **parametrizada por payload**: o mesmo motor (rotas em
`api/routes/auditoria.py`) atende qualquer contribuinte — basta passar
um JSON com seus dados.

## Como adicionar um novo cliente

1. Copie o modelo:
   ```
   cp scripts/clientes/_modelo_cliente.json \
      scripts/clientes/<slug-do-novo-cliente>.json
   ```

2. Preencha os campos:
   - **Identificação**: `contribuinte_cpf`, `contribuinte_nome`,
     `contribuinte_ie`, `municipio`, `estado`
   - **Período**: `periodo_inicio`, `periodo_fim`, `documento_base`
   - **Regime previdenciário**: `is_pj`, `is_segurado_especial`
     (afeta alíquota Funrural via LC 224/2025)
   - **Totais agregados** (`totais_planilha`, `totais_pdf_gief`):
     volume bruto, receita imediata, trânsito, cabeças, qtd notas etc.
     Quando o indicador não consta na fonte fazendária, omita-o do
     `totais_pdf_gief` — vira "Dado novo" no T-08.
   - **Mensais** (`vendas_mensais`, `remessas_mensais`, `compras_mensais`):
     lista por mês para a Planilha de Gado IR.
   - **Funrural**: estimativa e alíquota formatada (`"1,50%"`).
   - **Achados críticos**: lista opcional. Cada item pode ter
     `tabela_cabecalhos`/`tabela_linhas`/`tabela_totais` para reproduzir
     blocos como C-01 (operação singular), C-10 (smurfing), C-03 (leilão),
     A-01 (concentração PF) etc.

3. Rode:
   ```
   python scripts/gerar_auditoria.py <slug-do-novo-cliente>
   ```

4. Resultado em `outputs/<slug>/`:
   - `auditoria_cruzada.json` — resposta da API
   - `planilha_gado_ir_v5.docx` — Word da planilha
   - `auditoria_cruzada.pdf` — relatório completo (~14 págs)
   - `auditoria_simplificada.pdf` — versão de 6 páginas
   - `relatorio_resumo.md` — sumário humano-legível

## Processamento em batch

```
python scripts/gerar_auditoria.py --todos
```

Itera por todos os `*.json` em `scripts/clientes/` (ignora arquivos
começados com `_`, como o modelo).

## Arquivos atuais

| Arquivo | Cliente | Descrição |
|---|---|---|
| `genis_2025.json` | GENIS CARLOS LUIZ DE OLIVEIRA | Caso real do PDF v3 (CAMPINORTE/GO, 2025) |
| `exemplo_basico.json` | JOSE EXEMPLO DA SILVA | Cliente fictício mínimo (formato) |
| `_modelo_cliente.json` | — | Template para novos clientes |

## Schema do payload

O JSON deve seguir o pydantic-model `CruzamentoRequest` definido em
[api/routes/auditoria.py](../../api/routes/auditoria.py). Campos extras
no `_meta` são opcionais e ignorados pela API.
