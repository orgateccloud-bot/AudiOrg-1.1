"""Testes do prompt_compactor — codificação densa para reduzir tokens."""
from horizon_blue_one.core.prompt_compactor import (
    flags,
    kv,
    resumo_detectores,
    resumo_notas,
    tsv,
)


class TestKv:
    def test_chaves_basicas(self):
        out = kv({"a": 1, "b": "x"})
        assert "a=1" in out and "b=x" in out
        assert " | " in out

    def test_remove_vazios(self):
        out = kv({"a": 1, "b": None, "c": "", "d": [], "e": {}})
        assert "a=1" in out
        assert "b" not in out and "c" not in out and "d" not in out and "e" not in out

    def test_float_2_casas(self):
        assert kv({"x": 1.23456}) == "x=1.23"

    def test_bool_sim_nao(self):
        out = kv({"ok": True, "falha": False})
        assert "ok=sim" in out
        assert "falha=nao" in out

    def test_lista_e_dict_mostram_tamanho(self):
        out = kv({"itens": [1, 2, 3], "config": {"a": 1, "b": 2}})
        assert "itens=[3]" in out
        assert "config={2}" in out

    def test_separador_customizado(self):
        assert kv({"a": 1, "b": 2}, sep=";") == "a=1;b=2"


class TestTsv:
    def test_cabecalho_e_linhas(self):
        out = tsv(
            [{"n": "1", "v": 100.0}, {"n": "2", "v": 200.0}],
            ["n", "v"],
        )
        linhas = out.split("\n")
        assert linhas[0] == "n\tv"
        assert linhas[1] == "1\t100.00"
        assert linhas[2] == "2\t200.00"

    def test_chave_ausente_vira_vazio(self):
        out = tsv([{"a": 1}], ["a", "b"])
        assert "1\t" in out

    def test_vazio_retorna_so_cabecalho(self):
        out = tsv([], ["a", "b"])
        assert out == "a\tb"


class TestFlags:
    def test_ativas_concatenadas(self):
        out = flags({"a": True, "b": False, "c": True})
        assert "a" in out and "c" in out
        assert "b" not in out

    def test_lista_vazia_nao_conta(self):
        assert flags({"a": []}) == "nenhuma"

    def test_lista_com_itens_conta(self):
        out = flags({"fantasma": ["X"], "ok": False})
        assert "fantasma" in out

    def test_sem_ativas(self):
        assert flags({"a": False, "b": False}) == "nenhuma"


class TestResumoDetectores:
    def test_todas_flags(self):
        det = {
            "carrossel": True, "smurfing": True,
            "devolucao_posterior": True, "anomalia_temporal": True,
            "fornecedor_fantasma": ["A", "B"],
        }
        out = resumo_detectores(det)
        assert "carrossel=sim" in out
        assert "smurfing=sim" in out
        assert "fornecedor_fantasma=2" in out

    def test_dict_vazio(self):
        out = resumo_detectores({})
        assert "carrossel=nao" in out
        assert "fornecedor_fantasma=0" in out

    def test_fornecedor_fantasma_como_truthy_nao_lista(self):
        out = resumo_detectores({"fornecedor_fantasma": True})
        assert "fornecedor_fantasma=1" in out


class TestResumoNotas:
    def test_aplica_limite_default(self):
        notas = [{"numero": str(i)} for i in range(30)]
        out = resumo_notas(notas)
        linhas = out.split("\n")
        # 1 cabecalho + 20 linhas
        assert len(linhas) == 21

    def test_limite_customizado(self):
        notas = [{"numero": str(i)} for i in range(10)]
        out = resumo_notas(notas, limite=3)
        assert len(out.split("\n")) == 4  # cabecalho + 3
