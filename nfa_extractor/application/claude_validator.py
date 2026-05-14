"""
claude_validator.py — P3-B: Validador pós-extração + gerador de parecer narrativo.

Integra Claude em dois pontos do pipeline:
1. Validação de notas com baixa confiança (ExtractionOrchestrator → Claude)
2. Geração de parecer fiscal narrativo para inserção no relatório PDF

Ambos usam model_adapter.py com retry + prompt caching.
Protocolo @Delta: anonimiza PII antes de enviar a Claude.
"""

from typing import Optional, Dict, Any
import json
import logging

from horizon_blue_one.core.model_adapter import call_model, ModelType
from horizon_blue_one.core.privacy import anonymize_pii
from nfa_extractor.domain.extractor import NFA

logger = logging.getLogger(__name__)


class ValidadorExtracao:
      """Valida notas extraídas e gera parecer narrativo para auditoria fiscal."""

    async def validar_nota_com_claude(self, nfa: NFA) -> Dict[str, Any]:
              """
                      Valida uma nota com baixa confiança usando Claude.

                                      Usado pelo ExtractionOrchestrator quando confidence_score < 0.70.
                                              Retorna dict com: confianca_validacao, campos_corretos, avisos, sugestoes
                                                      """
              try:
                            # Anonimizar antes de enviar
                            nfa_dict = nfa.dict()
                            nfa_anon, _, _, _ = anonymize_pii(json.dumps(nfa_dict))

            prompt = f"""Analise a seguinte Nota Fiscal (dados anonimizados) e valide a extracao:
            {nfa_anon}

            Retorne APENAS JSON valido com estrutura:
            {{"confianca_validacao": 0.0-1.0, "campos_corretos": [...], "avisos": [...], "sugestoes": [...]}}"""

            resp = await call_model(
                              ModelType.HAIKU,  # modelo menor, mais rapido para validacao
                              prompt,
                              system="Validador de extracao de PDFs NFA-e. Retorne APENAS JSON valido.",
                              max_tokens=512
            )
            return json.loads(resp)
except Exception as e:
            logger.error(f"Erro ao validar com Claude: {e}")
            return {"confianca_validacao": 0.0, "avisos": [str(e)]}

    async def gerar_parecer_narrativo(self, resumo_fiscal: Dict[str, Any]) -> str:
              """
                      Gera parecer narrativo do laudo fiscal para insercao no PDF.

                                      Entrada: resumo consolidado da auditoria (scores, anomalias, FUNRURAL, etc)
                                              Saída: texto formatado em portugues, ~300-500 palavras, tom formal

                                                              Usado na geracao do relatorio PDF final (pdf_engine/orgaudi/report_builder.py)
                                                                      """
              try:
                            # Anonimizar resumo antes de enviar
                            resumo_anon, _, _, _ = anonymize_pii(json.dumps(resumo_fiscal, ensure_ascii=False))

            system_prompt = """Voce eh auditor fiscal senior e parecer consultant.
            Objetivo: redigir parecer tecnico de auditoria (Notas Fiscais Avulsas rurais).
            Estrutura OBRIGATORIA:
            1. Situacao encontrada (fatos objetivos)
            2. Analise tecnica (normas SEFAZ-GO, FUNRURAL 2026, anomalias detectadas)
            3. Conclusao e recomendacoes
            4. Ressalvas (se houver risco fiscal)

            Tom: formal, tecnico, sem jargao desnecessario.
            Comprimento: 300-500 palavras.
            Idioma: portugues brasileiro.
            Nunca mencione dados anonimizados (@DELTA, @PESSOA, @EMPRESA) — use referencias genericas como "contribuinte", "fornecedor", etc."""

            prompt = f"""Com base nos seguintes dados de auditoria fiscal (anonimizados):
            {resumo_anon}

            Gere um parecer tecnico de auditoria para Notas Fiscais Avulsas de produtor rural, seguindo a estrutura obrigatoria."""

            parecer = await call_model(
                              ModelType.SONNET,  # modelo maior para melhor qualidade redacional
                              prompt,
                              system=system_prompt,
                              max_tokens=1536
            )
            return parecer
except Exception as e:
            logger.error(f"Erro ao gerar parecer: {e}")
            return f"[ERRO NA GERACAO DO PARECER: {e}]"
