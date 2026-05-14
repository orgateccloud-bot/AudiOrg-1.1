# Melhorias — horizon_blue_one, nfa_extractor e pdf_engine

> Documento de referência das melhorias aplicadas em 2026-05-14 aos três
> módulos principais do OrgAudi Sovereign. Cada melhoria está rastreável
> ao commit correspondente no histórico de \`main\`.

## Visão geral

A análise abrangeu as três pastas a partir do mapeamento completo dos
arquivos, leitura do conteúdo e identificação de débitos técnicos.
Foram priorizadas melhorias com baixo risco de regressão e alto valor
operacional: observabilidade (métricas Prometheus, tokens consumidos),
robustez de I/O (cross-platform PDF rendering, fallback WeasyPrint),
LGPD (mais detectores de PII) e qualidade de validação (CPF/CNPJ real).

---

## horizon_blue_one

### \`core/config.py\` — credenciais Supabase

- Adicionadas as variáveis \`SUPABASE_URL\`, \`SUPABASE_ANON_KEY\`,
  \`SUPABASE_SERVICE_ROLE_KEY\` e \`SUPABASE_JWT_SECRET\`.
- Default de \`SUPABASE_URL\` aponta para o projeto real
  \`https://bfumcgchpwtbukahvbng.supabase.co\` (sa-east-1).
- Propriedade \`supabase_configurado\` retorna True quando as chaves estão
  injetadas via env ou \`config.env\`.

### \`core/model_adapter.py\` — observabilidade de custo

- Função \`_log_usage\` registra structurado \`input_tokens\`,
  \`output_tokens\`, \`cache_read_tokens\` e \`cache_create_tokens\` em cada
  chamada — essencial para auditar custos do Anthropic.
- Integração opcional com \`horizon_blue_one.core.metrics\`: contadores
  Prometheus alimentados automaticamente sem quebrar quando o pacote
  não está disponível.

### \`core/metrics.py\` (novo)

- Módulo dedicado a contadores e histogramas Prometheus:
  - \`MODEL_TOKENS_IN\` / \`MODEL_TOKENS_OUT\` / \`MODEL_LATENCY\` (LLM)
  - \`LEDGER_INSERTS\` / \`LEDGER_FALLBACKS\` (auditoria)
  - \`ROUTER_DECISIONS\` (token_router)
  - \`PDF_BUILDS\` / \`PDF_BUILD_LATENCY\` (pdf_engine)
- Stub no-op quando \`prometheus_client\` não está instalado — zero
  dependência obrigatória nova.

### \`core/privacy.py\` — mais detectores de PII

- Adicionadas regex para \`TELEFONE\` (BR fixo/celular, com/sem DDI/DDD),
  \`PLACA\` Mercosul e \`CEP\`.
- \`anonymize_pii\` agora retorna um dict tipado com todas as categorias.
- Campos textuais sensíveis ampliados (\`endereco\`, \`logradouro\`,
  \`complemento\`).
- Log estruturado emite hashes SHA-256 de todas as novas categorias.

---

## nfa_extractor

### \`utils/validators.py\` — validação real

- Acrescentadas funções \`validar_cpf\` e \`validar_cnpj\` com cálculo
  completo de dígito verificador (mesmo algoritmo de
  \`pdf_engine.orgaudi.validators\`).
- \`validar_documento\` faz a seleção automática por comprimento.
- Helpers de máscara: \`mascara_cpf\`, \`mascara_cnpj\`, \`mascara_documento\`.
- API legada (\`clean_document\`, \`format_currency\`, \`parse_brl_to_float\`)
  mantida para compatibilidade.

### \`application/audit_service.py\` — refactor

- Removido o duplo \`import\` (try/except contendo o mesmo trio de imports).
- Substituídas as f-strings nos calls do \`logger\` por argumentos lazy
  (padrão recomendado: o formatter só é aplicado se o log for emitido).
- Docstring formal com seções Args / Returns / Raises.
- Captura do gap de quantidades em variável intermediária para legibilidade.

---

## pdf_engine

### \`orgaudi/renderer.py\` — cross-platform e fallback

- Antes: hardcoded para o Chrome do Windows (\`C:\Program Files\Google\Chrome\...\`).
- Agora: estratégia de busca em 3 camadas:
  1. \`\$CHROME_BIN\` (override explícito — ideal para containers).
  2. \`shutil.which\` em PATH (chrome, chromium, google-chrome, msedge).
  3. Caminhos conhecidos por SO (Windows, macOS, Linux).
- Fallback opcional para **WeasyPrint** se Chrome falhar/inexistente.
- Integração com métricas Prometheus (\`PDF_BUILDS\`, \`PDF_BUILD_LATENCY\`).
- Erro final claro indicando que \`Chrome/Chromium\` ou \`WeasyPrint\`
  precisam estar disponíveis.

---

## Lista de commits

| Hash       | Arquivo / módulo                    | Tipo            |
|------------|-------------------------------------|-----------------|
| \`6ad4fec\`  | horizon_blue_one/core/config.py     | feat (config)   |
| \`608c056\`  | horizon_blue_one/core/model_adapter.py | feat (obs)   |
| \`b3f995d\`  | horizon_blue_one/core/metrics.py    | feat (novo)     |
| \`ebe2ccc\`  | horizon_blue_one/core/privacy.py    | feat (privacy)  |
| \`3a71d0f\`  | nfa_extractor/utils/validators.py   | feat (validators) |
| \`c016849\`  | nfa_extractor/application/audit_service.py | refactor |
| \`8f9b44c\`  | pdf_engine/orgaudi/renderer.py      | feat (renderer) |

---

## Próximas oportunidades (não implementadas)

- **Unificar \`logging_config.py\` de \`nfa_extractor\` com \`structlog\` do
  \`horizon_blue_one\`** — atualmente convivem dois sistemas (stdlib e
  structlog), o que dificulta correlação de logs.
- **Migrar \`ai_client.py\` para o \`model_adapter\` do horizon_blue_one** —
  remove a duplicação de cliente HTTP/retry e centraliza prompt caching.
- **Substituir os \`object.__setattr__\` em \`sovereign_engine.py\`** por
  reconstrução imutável do DTO (pattern Pydantic frozen \`model_copy(update=...)\`).
- **Consolidar \`validators.py\` (nfa_extractor) e \`validators.py\`
  (pdf_engine)** num único módulo compartilhado em \`shared/\` ou
  \`horizon_blue_one.core\`.
- **Adicionar testes de regressão para o renderer cross-platform**
  (mock de \`shutil.which\` e \`subprocess.run\`).
