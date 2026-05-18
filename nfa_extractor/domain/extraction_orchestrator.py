"""
ExtractionOrchestrator — P1-A: Orquestração unificada de extração de PDFs NFA-e.

Estratégia híbrida em cascata:
1. Tenta extractor.py (rápido, sem dependência de IA)
2. Calcula confidence_score para cada nota
3. Para notas com confidence < LIMIAR_CONFIANCA: aciona nfa_parser_ai.py (Claude como validador)
4. Consolida resultados com rastreabilidade

Resolve o problema arquitetural de ter dois parsers paralelos sem orquestração.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional, Tuple

from nfa_extractor.domain.extractor import NFA, extrair_notas, resumo_geral
from nfa_extractor.domain.nfa_parser_ai import extrair_pdf

logger = logging.getLogger(__name__)

# Limiar de confiança para escalação a Claude
LIMIAR_CONFIANCA_ESCALACAO: float = 0.70


class ExtractionResult:
      """Resultado consolidado de extração de notas."""

    def __init__(self):
              self.notas: List[NFA] = []
              self.nome_produtor: str = ""
              self.cpf_produtor: str = ""
              self.total_notas: int = 0
              self.notas_extracao_rapida: int = 0
              self.notas_extracao_ia: int = 0
              self.confianca_media: float = 0.0
              self.resumo: dict = {}
              self.erros: List[str] = []

    def to_dict(self) -> dict:
              """Exporta resultado como dicionário."""
              return {
                  "notas": [n.dict() for n in self.notas],
                  "nome_produtor": self.nome_produtor,
                  "cpf_produtor": self.cpf_produtor,
                  "total_notas": self.total_notas,
                  "notas_extracao_rapida": self.notas_extracao_rapida,
                  "notas_extracao_ia": self.notas_extracao_ia,
                  "confianca_media": round(self.confianca_media, 2),
                  "resumo": self.resumo,
                  "erros": self.erros,
              }


class ExtractionOrchestrator:
      """Orquestrador de extração NFA-e com dois estágios."""

    def __init__(self, limiar_escalacao: float = LIMIAR_CONFIANCA_ESCALACAO):
              self.limiar_escalacao = limiar_escalacao
              self.logger = logger

    async def extrair_pdf_completo(self, caminho_pdf: str | Path) -> ExtractionResult:
              """
                      Orquestra a extração de um PDF em duas camadas.

                              Etapas:
                                      1. Extração rápida (regex via extractor.py)
                                              2. Cálculo de confidence por nota
                                                      3. Escalação a Claude para notas com confidence < limiar
                                                              4. Consolidação e resumo

                                                                      Retorna: ExtractionResult com todas as notas e metadados.
                                                                              """
              resultado = ExtractionResult()
              caminho = Path(caminho_pdf)

        if not caminho.exists():
                      resultado.erros.append(f"Arquivo não encontrado: {caminho}")
                      return resultado

        self.logger.info(f"[EXTRACTOR] Iniciando orquestração: {caminho.name}")

        try:
                      # Etapa 1: Extração rápida (regex)
                      notas_rapidas, nome_prod, cpf_prod = extrair_notas(str(caminho))
                      resultado.nome_produtor = nome_prod
                      resultado.cpf_produtor = cpf_prod
                      resultado.notas_extracao_rapida = len(notas_rapidas)

            self.logger.info(
                              f"[EXTRACTOR] Etapa 1 concluída: {len(notas_rapidas)} notas extraídas via regex"
            )

            # Etapa 2: Separar por confiança
            notas_validadas = []
            notas_para_ia = []

            for nfa in notas_rapidas:
                              if nfa.confidence_score >= self.limiar_escalacao:
                                                    notas_validadas.append(nfa)
else:
                      notas_para_ia.append(nfa)

            self.logger.info(
                              f"[EXTRACTOR] Notas de alta confiança: {len(notas_validadas)}, "
                              f"Notas para IA: {len(notas_para_ia)}"
            )

            # Etapa 3: Escalação a Claude para notas de baixa confiança
            if notas_para_ia:
                              self.logger.info(
                                                    f"[EXTRACTOR] Escalando {len(notas_para_ia)} notas a Claude (P1-B validador)"
                              )
                              notas_validadas_ia = await self._validar_com_claude(
                                  notas_para_ia, str(caminho)
                              )
                              notas_validadas.extend(notas_validadas_ia)
                              resultado.notas_extracao_ia = len(notas_validadas_ia)

            # Etapa 4: Consolidação
            resultado.notas = notas_validadas
            resultado.total_notas = len(notas_validadas)
            resultado.confianca_media = (
                              sum(n.confidence_score for n in notas_validadas) / resultado.total_notas
                              if resultado.total_notas > 0
                              else 0.0
            )
            resultado.resumo = resumo_geral(notas_validadas, nome_prod)

            self.logger.info(
                              f"[EXTRACTOR] Orquestração concluída: {resultado.total_notas} notas "
                              f"(confiança média: {resultado.confianca_media:.2f})"
            )

except Exception as e:
            self.logger.error(f"[EXTRACTOR] Erro na orquestração: {e}")
            resultado.erros.append(f"Erro durante extração: {str(e)}")

        return resultado

    async def _validar_com_claude(
              self, notas: List[NFA], caminho_pdf: str
    ) -> List[NFA]:
              """
                      Valida notas de baixa confiança usando Claude (P1-B validador).

                              Claude recebe:
                                      - Notas com campos extraídos (mas incompletos)
                                              - PDF original para re-extração seletiva se necessário

                                                      Retorna notas com confidence_score atualizado.
                                                              """
              try:
                            # Usar nfa_parser_ai.extrair_pdf para re-extração via Claude
                            # com foco nas notas específicas que falharam
                            self.logger.info(
                                              f"[CLAUDE-VALIDADOR] Enviando {len(notas)} notas para validação"
                            )

                  # Chamar parser AI (que já integra Claude com tool_use e prompt caching)
                            nome_prod, cpf_prod, notas_ia = await extrair_pdf(caminho_pdf)

            # Mesclar resultados: usar notas_ia onde confidence > notas originais
            notas_consolidadas = []
            for nota_original in notas:
                              # Procurar correspondência na resposta do Claude (por chave ou número)
                              nota_ia = next(
                                                    (
                                                                              n
                                                                              for n in notas_ia
                                                                              if n.chave_acesso == nota_original.chave_acesso
                                                                              or n.numero == nota_original.numero
                                                    ),
                                                    None,
                              )

                if nota_ia and nota_ia.confidence_score > nota_original.confidence_score:
                                      # Claude melhorou a confiança
                                      notas_consolidadas.append(nota_ia)
                                      self.logger.info(
                                          f"[CLAUDE-VALIDADOR] Nota {nota_original.numero} melhorada: "
                                          f"{nota_original.confidence_score:.2f} → {nota_ia.confidence_score:.2f}"
                                      )
else:
                    # Mantém nota original
                      notas_consolidadas.append(nota_original)

            return notas_consolidadas

except Exception as e:
            self.logger.error(f"[CLAUDE-VALIDADOR] Erro na validação: {e}")
            # Fallback: retorna notas originais
            return notas

    def extrair_pdf_sincrono(self, caminho_pdf: str | Path) -> ExtractionResult:
              """Wrapper síncrono (para compatibilidade com código legado)."""
        import asyncio

        try:
                      loop = asyncio.get_event_loop()
except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(self.extrair_pdf_completo(caminho_pdf))
