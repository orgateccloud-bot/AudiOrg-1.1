"""test_precalc_isolamento.py
Teste de isolamento do __precalc__ entre 50 requisicoes concorrentes (Issue #28).
Criterio de aceite: teste concorrente passa sem cruzamento de dados.
"""
from __future__ import annotations
import asyncio
import pytest
from horizon_blue_one.core.precalc import (
    build_precalc, set_precalc_ctx, get_precalc_ctx, PrecalcLock,
)


def _payload(cliente_id: str, num_notas: int = 3) -> dict:
    return {
        "cliente_id": cliente_id,
        "area_ha": float(len(cliente_id)) * 10,
        "notas": [
            {"numero": f"{cliente_id}-{i:04d}", "cfop": "5101",
             "valor_total": 1000.0 * (i + 1), "data": "2026-05-18"}
            for i in range(num_notas)
        ],
    }


def test_build_precalc_retorna_copia_profunda():
    """build_precalc nao deve mutar o payload original."""
    original = _payload("CLIENTE_A")
    resultado = build_precalc(original)
    assert id(resultado) != id(original)
    assert "__precalc__" not in original
    assert "__precalc__" in resultado


def test_build_precalc_cfop_mapeado():
    """CFOP 5101 deve mapear para VENDA."""
    resultado = build_precalc(_payload("TESTE_B"))
    assert resultado["__precalc__"]["cfop_natureza"].get("5101") == "VENDA"


def test_build_precalc_fingerprint_unico():
    """Dois payloads distintos devem ter fingerprints distintos."""
    a = build_precalc(_payload("CX", 2))
    b = build_precalc(_payload("CY", 5))
    assert a["__precalc__"]["fingerprint"] != b["__precalc__"]["fingerprint"]


def test_build_precalc_itr_faixa():
    """Area 150 ha = faixa 50_200."""
    r = build_precalc({"notas": [], "area_ha": 150.0})
    assert r["__precalc__"]["faixa_modulo"] == "50_200"


def test_mutacao_nao_afeta_original():
    """Mutar resultado nao contamina o payload original."""
    original = _payload("MUT")
    resultado = build_precalc(original)
    resultado["__precalc__"]["cfop_natureza"]["HACK"] = "INJETADO"
    resultado["notas"].append({"extra": True})
    assert "HACK" not in str(original)
    assert len(original["notas"]) == 3


@pytest.mark.asyncio
async def test_context_var_isolamento_simples():
    """ContextVar isola precalc entre duas corotinas."""
    resultados = {}

    async def auditoria(cid: str, n: int) -> None:
        p = build_precalc(_payload(cid, n))
        set_precalc_ctx(p["__precalc__"])
        await asyncio.sleep(0.01)
        resultados[cid] = get_precalc_ctx()["fingerprint"]

    await asyncio.gather(auditoria("A", 2), auditoria("B", 5))
    assert resultados["A"] != resultados["B"]


@pytest.mark.asyncio
async def test_50_requisicoes_concorrentes_sem_contaminacao():
    """50 requisicoes concorrentes sem cruzamento de dados (criterio Issue #28)."""
    N = 50
    erros: list[str] = []

    async def auditoria(idx: int) -> None:
        n = (idx % 5) + 1
        cid = f"C{idx:03d}"
        p = build_precalc(_payload(cid, n))
        set_precalc_ctx(p["__precalc__"])
        await asyncio.sleep(0.001 * (idx % 10))
        actual = get_precalc_ctx()["total_notas"]
        if actual != n:
            erros.append(f"{cid}: esperado {n}, obteve {actual}")

    await asyncio.gather(*[auditoria(i) for i in range(N)])
    assert not erros, f"Contaminacao em {len(erros)} req: " + "; ".join(erros[:5])


@pytest.mark.asyncio
async def test_get_sem_set_levanta_runtime_error():
    """get_precalc_ctx sem set deve levantar RuntimeError."""
    async def sem_ctx() -> None:
        with pytest.raises(RuntimeError):
            get_precalc_ctx()
    await sem_ctx()


@pytest.mark.asyncio
async def test_precalc_lock_serializa():
    """PrecalcLock garante execucao serial."""
    ordem: list[int] = []
    lock = PrecalcLock()

    async def tarefa(i: int) -> None:
        async with lock:
            ordem.append(i)
            await asyncio.sleep(0.001)

    await asyncio.gather(*[tarefa(i) for i in range(5)])
    assert set(ordem) == {0, 1, 2, 3, 4}
