"""Testes da ponte nfa_repo → horizon_blue_one (CFOP heurístico, agrupamento)."""
from unittest.mock import MagicMock

from horizon_blue_one.nfa_bridge import (
    _nome_produtor,
    agrupar_pdfs_por_produtor,
    cfop_heuristico,
    classificar_natureza,
    nfa_to_dict,
)

# ── cfop_heuristico ──────────────────────────────────────────────────────────

class TestCfopHeuristico:
    def test_venda_remetente_5102(self):
        assert cfop_heuristico("VENDA", "REMETENTE") == "5102"

    def test_venda_destinatario_1102(self):
        assert cfop_heuristico("VENDA", "DESTINATARIO") == "1102"

    def test_remessa_remetente_5949(self):
        assert cfop_heuristico("REMESSA", "REMETENTE") == "5949"

    def test_remessa_destinatario_1949(self):
        assert cfop_heuristico("REMESSA", "DESTINATARIO") == "1949"

    def test_transferencia_remetente_5152(self):
        assert cfop_heuristico("TRANSFERENCIA", "REMETENTE") == "5152"

    def test_natureza_desconhecida_cai_em_outras(self):
        # "PRESTACAO" não bate em VENDA/REMESSA/TRANSFER → OUTRAS → 5949
        assert cfop_heuristico("PRESTACAO", "REMETENTE") == "5949"

    def test_case_insensitive(self):
        assert cfop_heuristico("venda", "remetente") == "5102"
        assert cfop_heuristico("Venda", "DesTinaTario") == "1102"

    def test_natureza_com_prefixo_venda(self):
        # "VENDA DE GADO BOVINO" → contém VENDA → 5102
        assert cfop_heuristico("VENDA DE GADO", "REMETENTE") == "5102"

    def test_natureza_vazia_fallback(self):
        assert cfop_heuristico("", "REMETENTE") == "5949"

    def test_posicao_vazia_assume_remetente(self):
        # Default → REMETENTE
        assert cfop_heuristico("VENDA", "") == "5102"

    def test_destinatario_abreviado(self):
        # "DESTIN" deveria bater (contém "DESTIN")
        assert cfop_heuristico("VENDA", "DESTIN") == "1102"


# ── classificar_natureza ─────────────────────────────────────────────────────

class TestClassificarNatureza:
    def test_venda_de_gado(self):
        assert classificar_natureza("VENDA DE GADO BOVINO") == "VENDA"

    def test_remessa_para_recria(self):
        assert classificar_natureza("REMESSA PARA RECRIA") == "REMESSA"

    def test_transferencia(self):
        assert classificar_natureza("TRANSFERENCIA DE GADO") == "TRANSFERENCIA"

    def test_transferência_com_acento(self):
        assert classificar_natureza("TRANSFERÊNCIA INTERNA") == "TRANSFERENCIA"

    def test_outras_para_natureza_desconhecida(self):
        assert classificar_natureza("PRESTACAO DE SERVICO") == "OUTRAS"

    def test_string_vazia_outras(self):
        assert classificar_natureza("") == "OUTRAS"

    def test_none_tratado(self):
        assert classificar_natureza(None) == "OUTRAS"

    def test_case_insensitive(self):
        assert classificar_natureza("venda de bovinos") == "VENDA"


# ── _nome_produtor (parsing de nome de arquivo) ──────────────────────────────

class TestNomeProdutor:
    def test_arquivo_rem(self, tmp_path):
        pdf = tmp_path / "ADELA REM.pdf"
        pdf.touch()
        nome, pos = _nome_produtor(pdf)
        assert nome == "ADELA"
        assert pos == "REMETENTE"

    def test_arquivo_dest(self, tmp_path):
        pdf = tmp_path / "JOAO SILVA DEST.pdf"
        pdf.touch()
        nome, pos = _nome_produtor(pdf)
        assert nome == "JOAO SILVA"
        assert pos == "DESTINATARIO"

    def test_arquivo_sem_padrao_retorna_vazio(self, tmp_path):
        pdf = tmp_path / "qualquer.pdf"
        pdf.touch()
        nome, pos = _nome_produtor(pdf)
        assert nome == ""
        assert pos == ""

    def test_case_insensitive(self, tmp_path):
        pdf = tmp_path / "MARIA rem.pdf"
        pdf.touch()
        nome, pos = _nome_produtor(pdf)
        assert nome == "MARIA"
        assert pos == "REMETENTE"


# ── agrupar_pdfs_por_produtor ─────────────────────────────────────────────────

class TestAgruparPdfs:
    def test_agrupa_rem_e_dest_do_mesmo_produtor(self, tmp_path):
        (tmp_path / "JOAO REM.pdf").touch()
        (tmp_path / "JOAO DEST.pdf").touch()
        (tmp_path / "MARIA REM.pdf").touch()

        grupos = agrupar_pdfs_por_produtor(tmp_path)

        assert "JOAO" in grupos
        assert "MARIA" in grupos
        assert len(grupos["JOAO"]["REMETENTE"]) == 1
        assert len(grupos["JOAO"]["DESTINATARIO"]) == 1
        assert len(grupos["MARIA"]["REMETENTE"]) == 1
        assert len(grupos["MARIA"]["DESTINATARIO"]) == 0

    def test_ignora_arquivos_sem_padrao(self, tmp_path):
        (tmp_path / "JOAO REM.pdf").touch()
        (tmp_path / "outro_arquivo.pdf").touch()
        (tmp_path / "README.md").touch()

        grupos = agrupar_pdfs_por_produtor(tmp_path)
        assert list(grupos.keys()) == ["JOAO"]

    def test_pasta_vazia(self, tmp_path):
        assert agrupar_pdfs_por_produtor(tmp_path) == {}


# ── nfa_to_dict (conversão Pydantic-like → dict precalc) ─────────────────────

class TestNfaToDict:
    def _mock_nfa(self, **kwargs):
        nfa = MagicMock()
        nfa.numero = kwargs.get("numero", "123")
        nfa.emissao = kwargs.get("emissao", "01/01/2025")
        nfa.natureza = kwargs.get("natureza", "VENDA DE GADO")
        nfa.valor_total = kwargs.get("valor_total", 10000)
        nfa.valor_icms = kwargs.get("valor_icms", 1700)
        nfa.quantidade_total = kwargs.get("quantidade", 10)
        nfa.chave_acesso = kwargs.get("chave_acesso", "X" * 44)
        nfa.remetente = MagicMock(
            nome="REMETENTE LTDA", cpf_cnpj="12.345.678/0001-90", ie="123456",
        )
        nfa.destinatario = MagicMock(
            nome="DESTINATARIO SA", cpf_cnpj="98.765.432/0001-10", ie="654321",
        )
        return nfa

    def test_converte_campos_basicos(self):
        d = nfa_to_dict(self._mock_nfa(), "012.345.678-90", "REM")
        assert d["numero"] == "123"
        assert d["natureza"] == "VENDA"  # normalizada
        assert d["valor_total"] == 10000.0
        assert d["tipo_doc"] == "nfa-e"

    def test_posicao_remetente_aplica_cfop_saida(self):
        d = nfa_to_dict(self._mock_nfa(), "012.345.678-90", "REM")
        assert d["posicao"] == "REMETENTE"
        assert d["cfop"] == "5102"  # VENDA + REMETENTE

    def test_posicao_destinatario_aplica_cfop_entrada(self):
        d = nfa_to_dict(self._mock_nfa(), "012.345.678-90", "DEST")
        assert d["posicao"] == "DESTINATARIO"
        assert d["cfop"] == "1102"  # VENDA + DESTINATARIO

    def test_atividade_default_bovino(self):
        d = nfa_to_dict(self._mock_nfa(), "012.345.678-90", "REM")
        assert d["atividade"] == "bovino"

    def test_atividade_customizada(self):
        d = nfa_to_dict(self._mock_nfa(), "012.345.678-90", "REM", atividade="soja")
        assert d["atividade"] == "soja"

    def test_contribuinte_cpf_propagado(self):
        d = nfa_to_dict(self._mock_nfa(), "999.888.777-66", "REM")
        assert d["contribuinte_cpf"] == "999.888.777-66"

    def test_valores_none_viram_zero(self):
        nfa = self._mock_nfa()
        nfa.valor_total = None
        nfa.valor_icms = None
        d = nfa_to_dict(nfa, "012.345.678-90", "REM")
        assert d["valor_total"] == 0.0
        assert d["valor_icms"] == 0.0
