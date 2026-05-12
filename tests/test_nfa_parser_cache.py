"""Testes do cache LRU de lotes Claude no parser NFA-e."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from nfa_extractor.domain import nfa_parser_ai as parser_mod
from nfa_extractor.domain.nfa_parser_ai import (
    _hash_lote,
    _parse_lote_claude,
    cache_reset,
    cache_stats,
)


@pytest.fixture(autouse=True)
def _zera_cache():
    cache_reset()
    yield
    cache_reset()


def _mock_client(notas: list[dict] | None = None, t_in: int = 100, t_out: int = 50):
    """Mock do cliente Anthropic — devolve uma resposta tool_use válida."""
    notas = notas or [{
        "numero": "12345", "emissao": "01/01/2025", "natureza": "VENDA",
        "valor_total": 100.0, "valor_icms": 0.0, "chave_acesso": "X" * 44,
        "remetente_nome": "FULANO", "remetente_cpf_cnpj": "11122233344",
        "remetente_municipio": "GOIANIA", "remetente_ie": "123456",
        "destinatario_nome": "BELTRANO", "destinatario_cpf_cnpj": "55566677788",
        "destinatario_municipio": "ANAPOLIS",
        "produtos": [],
    }]
    tool_block = SimpleNamespace(type="tool_use", input={"notas": notas})
    resp = SimpleNamespace(
        content=[tool_block],
        usage=SimpleNamespace(input_tokens=t_in, output_tokens=t_out),
    )
    client = MagicMock()
    client.messages.create.return_value = resp
    return client


class TestHashLote:
    def test_hash_estavel_para_mesma_entrada(self):
        h1 = _hash_lote("haiku", ["bloco-A", "bloco-B"])
        h2 = _hash_lote("haiku", ["bloco-A", "bloco-B"])
        assert h1 == h2

    def test_hash_muda_com_modelo(self):
        assert _hash_lote("haiku", ["x"]) != _hash_lote("sonnet", ["x"])

    def test_hash_muda_com_conteudo(self):
        assert _hash_lote("haiku", ["a"]) != _hash_lote("haiku", ["b"])

    def test_hash_muda_com_ordem_blocos(self):
        # Ordem importa — Claude pode dar resultados diferentes
        assert _hash_lote("haiku", ["a", "b"]) != _hash_lote("haiku", ["b", "a"])


class TestCacheHitMiss:
    def test_miss_na_primeira_chamada(self):
        client = _mock_client()
        notas, t_in, t_out = _parse_lote_claude(["bloco-X"], client, "haiku")

        assert len(notas) == 1
        assert t_in == 100 and t_out == 50
        assert client.messages.create.call_count == 1
        stats = cache_stats()
        assert stats["misses"] == 1
        assert stats["hits"] == 0
        assert stats["size"] == 1

    def test_hit_na_segunda_chamada(self):
        client = _mock_client()
        _parse_lote_claude(["bloco-X"], client, "haiku")
        notas2, t_in2, t_out2 = _parse_lote_claude(["bloco-X"], client, "haiku")

        # Cliente foi chamado apenas uma vez — segunda foi servida do cache
        assert client.messages.create.call_count == 1
        assert len(notas2) == 1
        assert (t_in2, t_out2) == (100, 50)
        stats = cache_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5

    def test_miss_com_blocos_diferentes(self):
        client = _mock_client()
        _parse_lote_claude(["A"], client, "haiku")
        _parse_lote_claude(["B"], client, "haiku")
        assert client.messages.create.call_count == 2
        assert cache_stats()["misses"] == 2

    def test_miss_com_modelos_diferentes(self):
        client = _mock_client()
        _parse_lote_claude(["A"], client, "haiku")
        _parse_lote_claude(["A"], client, "sonnet")
        assert client.messages.create.call_count == 2

    def test_lista_vazia_nao_consulta_cache(self):
        client = _mock_client()
        notas, t_in, t_out = _parse_lote_claude([], client, "haiku")
        assert (notas, t_in, t_out) == ([], 0, 0)
        assert client.messages.create.call_count == 0
        # Lista vazia nem incrementa miss
        assert cache_stats()["misses"] == 0


class TestCacheLRU:
    def test_evicta_quando_excede_max(self, monkeypatch):
        # Reduz o limite para forçar evicção sem inserir 257 entradas
        monkeypatch.setattr(parser_mod, "_PARSE_CACHE_MAX", 2)
        client = _mock_client()
        _parse_lote_claude(["A"], client, "haiku")
        _parse_lote_claude(["B"], client, "haiku")
        _parse_lote_claude(["C"], client, "haiku")
        # Após 3 inserções, cache deve ter no máximo 2
        assert cache_stats()["size"] == 2

    def test_hit_promove_para_mais_recente(self, monkeypatch):
        monkeypatch.setattr(parser_mod, "_PARSE_CACHE_MAX", 2)
        client = _mock_client()
        _parse_lote_claude(["A"], client, "haiku")  # cache: [A]
        _parse_lote_claude(["B"], client, "haiku")  # cache: [A, B]
        _parse_lote_claude(["A"], client, "haiku")  # hit A → cache: [B, A]
        _parse_lote_claude(["C"], client, "haiku")  # evicta B → cache: [A, C]

        # B deve ter sido evictado, mas A ainda hita
        assert client.messages.create.call_count == 3  # A, B, C — A nunca recall
        # Confirma que A continua em cache
        _parse_lote_claude(["A"], client, "haiku")
        assert client.messages.create.call_count == 3
        assert cache_stats()["hits"] >= 2


class TestCacheReset:
    def test_reset_limpa_tudo(self):
        client = _mock_client()
        _parse_lote_claude(["A"], client, "haiku")
        _parse_lote_claude(["A"], client, "haiku")
        cache_reset()
        stats = cache_stats()
        assert stats == {"hits": 0, "misses": 0, "size": 0, "hit_rate": 0.0}
