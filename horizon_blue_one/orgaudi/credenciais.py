"""
horizon_blue_one.orgaudi.credenciais
Fonte única da verdade para identificação do responsável técnico.
Todos os módulos (pdf_engine, report_builder, handlers) importam daqui.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Responsavel:
    nome: str
    formacao: str
    registro_crc: str
    empresa: str

    def linha_rodape(self) -> str:
        """Linha curta para rodapé do PDF."""
        return f"{self.nome} — {self.formacao} · CRC {self.registro_crc}"

    def linha_assinatura(self) -> str:
        """Bloco completo para página de assinatura."""
        return (
            f"{self.nome}\n"
            f"{self.formacao} · CRC {self.registro_crc}\n"
            f"{self.empresa}"
        )

    def linha_completa(self) -> str:
        """Linha única para metadados PDF."""
        return f"{self.nome} · {self.formacao} · CRC {self.registro_crc}"


RESPONSAVEL = Responsavel(
    nome="Robson Alain Veloso",
    formacao="Ciências Contábeis",
    registro_crc="TO-002032/O-5 T-GO",
    empresa="ORGATEC CONTABILIDADE E AUDITORIA",
)
