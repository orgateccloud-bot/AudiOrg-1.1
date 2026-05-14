# P3-A: Unificar ai_client.py com model_adapter.py

## Problema

Duplicacao de implementacao de IA client:
- `nfa_extractor/infrastructure/ai_client.py` usa HTTP bruto (requests.post)
- - `horizon_blue_one/core/model_adapter.py` usa SDK oficial Anthropic com retry + prompt caching
  - - Inconsistencia em qualidade, resiliencia e observabilidade
   
    - ## Solucao
   
    - Refatorar `ai_client.py` para usar `call_model()` do `model_adapter.py`
   
    - ## Mudancas Necessarias
   
    - ### Arquivo: nfa_extractor/infrastructure/ai_client.py
   
    - #### 1. Adicionar imports (linha ~1-20)
    - ```python
      from horizon_blue_one.core.model_adapter import call_model, ModelType
      from tenacity import retry, stop_after_attempt, wait_exponential
      ```

      #### 2. Remover
      ```python
      import requests  # linha ~19 — REMOVER
      ```

      #### 3. Refatorar funcao analisar_com_resumo()
      Substituir a implementacao que usa `requests.post()` por:

      ```python
      @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
      async def analisar_com_resumo(
          input_data: dict,
          system_prompt: str,
          nome_produtor: str = ""
      ) -> str:
          """
          Analisa resumo de notas usando Claude via SDK oficial (model_adapter.py).

          Substitui HTTP bruto por SDK oficial com:
          - Retry automatico (3 tentativas, backoff exponencial 1-8s)
          - Prompt caching (ephemeral cache no Anthropic)
          - Logging de metricas (tokens, latencia, cache hits)
          - Conformidade com tenacity (mesmo que A-07, A-08)
          """
          prompt = json.dumps(input_data, ensure_ascii=False)
          return await call_model(
              ModelType.SONNET,
              prompt,
              system=system_prompt,
              max_tokens=2048
          )
      ```

      ## Beneficios

      - ✅ Unificacao: unico client IA em model_adapter.py
      - - ✅ Resiliencia: retry automatico via tenacity
        - - ✅ Caching: prompt caching economiza tokens
          - - ✅ Observabilidade: metricas Prometheus + structlog
            - - ✅ Compatibilidade: mesmo modo que A-07, A-08 (HORIZON-BLUE ONE)
             
              - ## Teste
             
              - ```bash
                # Local (após mudanças)
                pytest tests/test_ai_client.py -v

                # Verificar que analisar_com_resumo() retorna string JSON
                ```

                ## Tempo Estimado

                5-10 min (edição + testes locais)

                ## Commit Message

                ```
                refactor(ai_client): P3-A unificar com model_adapter usando SDK oficial
                ```

                ---

                **Nota**: Esta é a ULTIMA fase (P3-A) que completa as 6 melhorias criticas identificadas.
                
