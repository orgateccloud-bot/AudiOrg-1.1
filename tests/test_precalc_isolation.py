"""Issue #28 — Isolamento de `__precalc__` em requisições concorrentes.

Cenários cobertos:

1. Mutação downstream em `__precalc__` (simula a08_geo/a26_anomalia escrevendo
   no resultado) NÃO contamina o memo cache compartilhado.
2. `reset_precalc_cache()` limpa o cache.
3. 50 requisições concorrentes (mesmo hash → todas pegam memo hit; CNPJs
   distintos → cada uma gera seu próprio precalc): cada uma observa um payload
   isolado, sem vazamento de estado entre tarefas.
"""
from __future__ import annotations

import asyncio
import copy

import pytest

from horizon_blue_one.core import precalc as pre_mod
from horizon_blue_one.core.precalc import precalcular, reset_precalc_cache


def _payload_base(cnpj: str = "00.000.000/0001-00") -> dict:
    return {
        "notas": [
            {
                "natureza":     "VENDA",
                "posicao":      "REMETENTE",
                "atividade":    "bovino",
                "tipo_doc":     "nfa-e",
                "valor_total":  1500.0,
                "cfop":         "5102",
                "numero":       "1",
                "chave_acesso": "X" * 44,
                "data":         "2026-01-15",
            }
        ],
        "contribuinte": {"cpf_cnpj": cnpj, "area_total_ha": 100, "area_utilizada_ha": 80},
        "lcdpr_data":   {},
    }


# ── 1. Mutação downstream não contamina cache compartilhado ─────────────────

class TestIsolamentoMutacao:
    @pytest.mark.asyncio
    async def test_mutacao_em_precalc_nao_contamina_cache(self):
        """Agente downstream muta __precalc__ → próxima requisição (mesmo hash)
        recebe versão limpa do cache, não a mutada."""
        reset_precalc_cache()

        # Primeira chamada popula o cache
        payload_a = _payload_base()
        out_a = await precalcular(payload_a)
        assert "__precalc__" in out_a
        out_a["__precalc__"]["xgboost"]["score"] = 9999
        out_a["__precalc__"]["notas_re1"].append({"injetado": "lixo"})

        # Segunda chamada com mesmo hash → memo hit, mas deve estar isolada
        payload_b = _payload_base()
        out_b = await precalcular(payload_b)
        assert out_b["__precalc__"]["xgboost"]["score"] != 9999
        assert all("injetado" not in n for n in out_b["__precalc__"]["notas_re1"])

    @pytest.mark.asyncio
    async def test_payloads_diferentes_nao_compartilham_estado(self):
        """Dois payloads com CNPJs distintos têm precalc independentes."""
        reset_precalc_cache()

        payload_a = _payload_base(cnpj="11.111.111/0001-11")
        payload_b = _payload_base(cnpj="22.222.222/0001-22")

        out_a = await precalcular(payload_a)
        out_b = await precalcular(payload_b)

        # São objetos distintos (não compartilham mesma referência)
        assert out_a["__precalc__"] is not out_b["__precalc__"]
        assert out_a["__precalc__"]["notas_re1"] is not out_b["__precalc__"]["notas_re1"]


# ── 2. reset_precalc_cache ──────────────────────────────────────────────────

class TestResetCache:
    @pytest.mark.asyncio
    async def test_reset_zera_memo_cache(self):
        reset_precalc_cache()
        await precalcular(_payload_base(cnpj="33.333.333/0001-33"))
        assert len(pre_mod._MEMO_CACHE) >= 1
        reset_precalc_cache()
        assert len(pre_mod._MEMO_CACHE) == 0


# ── 3. Concorrência: 50 requisições paralelas ───────────────────────────────

class TestConcorrencia:
    @pytest.mark.asyncio
    async def test_50_requisicoes_concorrentes_isoladas(self):
        """50 requisições concorrentes com CNPJs distintos → cada uma observa
        seu próprio precalc. Após todas concluírem, validar que cada resultado
        é íntegro e que mutações em uma não afetam outras."""
        reset_precalc_cache()

        async def _audit(idx: int) -> dict:
            payload = _payload_base(cnpj=f"99.{idx:03d}.{idx:03d}/0001-99")
            payload["notas"][0]["valor_total"] = 100.0 + idx
            payload["notas"][0]["numero"]      = str(idx)
            return await precalcular(payload)

        resultados = await asyncio.gather(*[_audit(i) for i in range(50)])

        # Asserções por resultado: precalc completo + valor_total preservado.
        for i, out in enumerate(resultados):
            assert "__precalc__" in out
            pre = out["__precalc__"]
            assert "notas_re1" in pre and len(pre["notas_re1"]) == 1
            assert pre["notas_re1"][0]["valor_total"] == 100.0 + i, (
                f"Vazamento em idx={i}: esperado {100.0 + i}, "
                f"obtido {pre['notas_re1'][0]['valor_total']}"
            )

        # Asserções entre resultados: nenhum compartilha referência com outro.
        for i in range(0, len(resultados), 10):
            for j in range(i + 1, min(i + 5, len(resultados))):
                assert resultados[i]["__precalc__"] is not resultados[j]["__precalc__"]
                assert (
                    resultados[i]["__precalc__"]["notas_re1"]
                    is not resultados[j]["__precalc__"]["notas_re1"]
                )

    @pytest.mark.asyncio
    async def test_memo_hit_concorrente_isolado(self):
        """Mesmo hash em N tarefas paralelas: o primeiro popula, os demais batem
        memo hit. Mutar o resultado de uma tarefa não pode vazar para outras."""
        reset_precalc_cache()

        # Aquece o cache uma vez (síncrono) para garantir que as próximas N
        # chamadas peguem memo hit deterministicamente.
        await precalcular(_payload_base(cnpj="77.777.777/0001-77"))

        async def _hit_e_mutar(idx: int) -> dict:
            out = await precalcular(_payload_base(cnpj="77.777.777/0001-77"))
            # Cada tarefa muta seu snapshot localmente
            out["__precalc__"]["xgboost"]["score"] = idx
            out["__precalc__"]["__marker__"] = idx
            return out

        resultados = await asyncio.gather(*[_hit_e_mutar(i) for i in range(20)])

        # Cada tarefa observou seu próprio score (sem corrupção cruzada)
        for i, out in enumerate(resultados):
            assert out["__precalc__"]["xgboost"]["score"] == i
            assert out["__precalc__"]["__marker__"] == i

        # Cache permanece íntegro (sem marcador injetado por nenhuma das tasks)
        out_pos = await precalcular(_payload_base(cnpj="77.777.777/0001-77"))
        assert "__marker__" not in out_pos["__precalc__"]
        assert out_pos["__precalc__"]["xgboost"]["score"] != 19  # nem o último
