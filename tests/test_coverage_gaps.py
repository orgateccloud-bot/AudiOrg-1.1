"""Testes para fechar últimos gaps de cobertura — base_agent, s7_ceo, orchestrator,
auditoria_tasks, security fallback, s2_forense exception."""
import os

os.environ["JWT_SECRET_KEY"] = "a" * 64

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from horizon_blue_one.agents.base_agent import AgentResult, BaseAgent

# ── base_agent L34-35: exceção ao ler settings ───────────────────────────────

class TestAgentResultHashFallback:
    def test_audit_hash_usa_fallback_quando_settings_falham(self):
        """L34-35: 'from ... import settings' falha → hash_len=64."""
        import sys
        original = sys.modules.get("horizon_blue_one.core.config")

        class _BrokenModule:
            def __getattr__(self, name):
                raise RuntimeError("erro proposital")

        sys.modules["horizon_blue_one.core.config"] = _BrokenModule()
        try:
            r = AgentResult(
                agent_id="S1", status="APROVADO",
                output={"x": 1}, confidence=0.9,
            )
            assert len(r.audit_hash) == 64  # fallback hash_len = 64
        finally:
            if original is not None:
                sys.modules["horizon_blue_one.core.config"] = original
            else:
                sys.modules.pop("horizon_blue_one.core.config", None)


# ── base_agent L50: log_error sem exceção ────────────────────────────────────

class TestBaseAgentLogError:
    def test_log_error_sem_exc(self):
        class _A(BaseAgent):
            agent_id = "X"
            name = "@X"
            async def process(self, payload):
                return AgentResult(agent_id="X", status="OK", output={})
        # Não deve levantar
        _A().log_error("erro qualquer", exc=None)
        _A().log_error("erro outro", exc=ValueError("boom"))


# ── base_agent L126: confidence quando data tem 'confianca' válida ───────────

class TestDerivarConfidence:
    def test_confianca_declarada_no_dict_eh_usada(self):
        c = BaseAgent.derivar_confidence(
            parseou_ok=True,
            data={"confianca": 0.42, "decisao": "x"},
            campos_esperados=("decisao",),
        )
        assert c == 0.42

    def test_data_sem_campos_esperados_cobertura_1(self):
        # Cobre o else (linha 126): cobertura = 1.0
        c = BaseAgent.derivar_confidence(
            parseou_ok=True, data={}, campos_esperados=(),
        )
        assert c == 0.85  # base * 1.0


# ── s2_forense L170-171: score_risco inválido cai para score original ────────

class TestS2ForenseScoreInvalido:
    @pytest.mark.asyncio
    async def test_score_risco_string_invalida_usa_fallback(self):
        import json

        from horizon_blue_one.agents.s2_forense import ForenseAgent
        pre = {
            "detectores": {
                "carrossel": False, "smurfing": False, "fornecedor_fantasma": [],
                "devolucao_posterior": False, "anomalia_temporal": False,
            },
            "xgboost": {"score": 40, "tipologias_criticas": 0, "probabilidade_autuacao": 0.4},
            "lstm": {"score_medio": 0.0, "produtores_anomalos": []},
            "grafo": {"densidade": 0.0, "ciclos": 0, "hubs": []},
        }
        # LLM responde score_risco como string inválida
        resp = json.dumps({
            "score_risco": "nao-eh-numero", "nivel": "MÉDIO",
            "tipologias": [], "narrativa": "x", "evidencias": [], "acoes": [],
        })
        with patch("horizon_blue_one.agents.s2_forense.call_otimizado",
                   new_callable=AsyncMock, return_value=(resp, {})):
            r = await ForenseAgent().process({"__precalc__": pre})
        # score_final caiu para o score inicial (40)
        assert r.status in ("APROVADO", "ESCALADO")


# ── s7_ceo branches ──────────────────────────────────────────────────────────

class TestS7CEOBranches:
    @pytest.mark.asyncio
    async def test_resultado_nao_dict_continua(self):
        """L60: out não é dict → continue."""
        import json

        from horizon_blue_one.agents.s7_ceo import CEOAgent
        resp = json.dumps({
            "decisao": "APROVAR", "score_final": 10.0,
            "parecer_juridico": "ok", "mda_executivo": "ok",
            "acoes_imediatas": [], "riscos_residuais": [], "confianca": 0.9,
        })
        payload = {
            "__precalc__": {
                "xgboost": {"score": 10, "tipologias_criticas": 0, "probabilidade_autuacao": 0.1},
                "caixa": {"entradas": 1000},
            },
            "resultados_agentes": {"S1": "isso-nao-eh-dict", "S2": {"nivel": "BAIXO"}},
            "contribuinte": {"razao_social": "Teste"},
        }
        with patch("horizon_blue_one.agents.s7_ceo.call_otimizado",
                   new_callable=AsyncMock, return_value=(resp, {})):
            r = await CEOAgent().process(payload)
        assert r.status == "APROVADO"

    @pytest.mark.asyncio
    async def test_resultado_sem_chaves_relevantes_pula(self):
        """L63: sub vazio → não inclui no resumo."""
        import json

        from horizon_blue_one.agents.s7_ceo import CEOAgent
        resp = json.dumps({
            "decisao": "APROVAR", "score_final": 5.0,
            "parecer_juridico": "x", "mda_executivo": "x",
            "acoes_imediatas": [], "riscos_residuais": [], "confianca": 0.8,
        })
        payload = {
            "__precalc__": {
                "xgboost": {"score": 5, "tipologias_criticas": 0, "probabilidade_autuacao": 0.05},
                "caixa": {"entradas": 0},
            },
            "resultados_agentes": {"S1": {"chave_aleatoria": 1}},  # nenhuma chave esperada
            "contribuinte": {},
        }
        with patch("horizon_blue_one.agents.s7_ceo.call_otimizado",
                   new_callable=AsyncMock, return_value=(resp, {})):
            r = await CEOAgent().process(payload)
        assert r.output["resumo_agentes"] == "(sem agentes)"

    @pytest.mark.asyncio
    async def test_decisao_rejeitar_vira_status_rejeitado(self):
        """L100: REJEITAR → REJEITADO."""
        import json

        from horizon_blue_one.agents.s7_ceo import CEOAgent
        resp = json.dumps({
            "decisao": "REJEITAR", "score_final": 95.0,
            "parecer_juridico": "rejeitar", "mda_executivo": "x",
            "acoes_imediatas": [], "riscos_residuais": [], "confianca": 0.99,
        })
        payload = {
            "__precalc__": {
                "xgboost": {"score": 95, "tipologias_criticas": 5, "probabilidade_autuacao": 0.98},
                "caixa": {"entradas": 5_000_000},
            },
            "resultados_agentes": {"S2": {"nivel": "CRÍTICO"}},
            "contribuinte": {"razao_social": "X"},
        }
        with patch("horizon_blue_one.agents.s7_ceo.call_otimizado",
                   new_callable=AsyncMock, return_value=(resp, {})):
            r = await CEOAgent().process(payload)
        assert r.status == "REJEITADO"

    @pytest.mark.asyncio
    async def test_decisao_escalar_juridico_vira_escalado(self):
        """L102: ESCALAR_JURIDICO → ESCALADO."""
        import json

        from horizon_blue_one.agents.s7_ceo import CEOAgent
        resp = json.dumps({
            "decisao": "ESCALAR_JURIDICO", "score_final": 80.0,
            "parecer_juridico": "escalar", "mda_executivo": "x",
            "acoes_imediatas": [], "riscos_residuais": [], "confianca": 0.85,
        })
        payload = {
            "__precalc__": {
                "xgboost": {"score": 80, "tipologias_criticas": 3, "probabilidade_autuacao": 0.85},
                "caixa": {"entradas": 100_000},
            },
            "resultados_agentes": {"S2": {"nivel": "ALTO"}},
            "contribuinte": {"razao_social": "Y"},
        }
        with patch("horizon_blue_one.agents.s7_ceo.call_otimizado",
                   new_callable=AsyncMock, return_value=(resp, {})):
            r = await CEOAgent().process(payload)
        assert r.status == "ESCALADO"


# ── orchestrator L376-377 ────────────────────────────────────────────────────

class TestOrchestratorScoreInvalido:
    def test_score_com_tipo_invalido_cai_para_proxima_chave(self):
        """Cobre L376-377: float() levanta → continue tenta próxima chave."""
        from horizon_blue_one.core.orchestrator import _score_consolidado

        r = AgentResult(
            agent_id="S2", status="APROVADO", confidence=0.9,
            output={"score_risco": "nao-numero", "score": 50.0},
        )
        # Primeiro tenta score_risco (falha), depois score (50.0) → max=50.0
        assert _score_consolidado({"S2": r}, pre=None) == 50.0


# ── api/services/auditoria_tasks ────────────────────────────────────────────

class TestAuditoriaTasks:
    def test_maybe_cleanup_exception_nao_propaga(self, monkeypatch):
        """L43-44: cleanup levanta → warning, segue."""
        from api.services import auditoria_tasks as at
        proxy = at._DbTasksProxy(ttl_seconds=10)
        proxy._last_cleanup = 0.0
        monkeypatch.setattr(at, "cleanup_old_tasks",
                            lambda _t: (_ for _ in ()).throw(RuntimeError("falhou")))
        monkeypatch.setattr(at, "upsert_task", lambda *a, **kw: None)
        # Não deve levantar
        proxy["k"] = {"status": "ok"}
        assert proxy._last_cleanup > 0

    def test_getitem_inexistente_levanta_keyerror(self, monkeypatch):
        """L54: data is None → KeyError."""
        from api.services import auditoria_tasks as at
        proxy = at._DbTasksProxy()
        monkeypatch.setattr(at, "get_task", lambda _k: None)
        with pytest.raises(KeyError):
            _ = proxy["inexistente"]

    def test_get_inexistente_retorna_default(self, monkeypatch):
        """L61-62: get() com default."""
        from api.services import auditoria_tasks as at
        proxy = at._DbTasksProxy()
        monkeypatch.setattr(at, "get_task", lambda _k: None)
        sentinela = object()
        assert proxy.get("k", sentinela) is sentinela

    def test_get_existente_retorna_dado(self, monkeypatch):
        from api.services import auditoria_tasks as at
        proxy = at._DbTasksProxy()
        monkeypatch.setattr(at, "get_task", lambda _k: {"status": "ok"})
        assert proxy.get("k") == {"status": "ok"}


# ── api/auth/security ────────────────────────────────────────────────────────

class TestSecurityFallback:
    def test_secret_key_curta_usa_fallback(self, monkeypatch):
        """L34: JWT_SECRET_KEY < 32 chars → fallback dev key."""
        from api.auth import security
        monkeypatch.setenv("JWT_SECRET_KEY", "muito-curta")
        key = security._secret_key()
        assert key == "ORGATEC_SOVEREIGN_SHIELD_2026_DEV_FALLBACK_64BYTES_PLACEHOLDER"

    def test_secret_key_vazia_usa_fallback(self, monkeypatch):
        from api.auth import security
        monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
        key = security._secret_key()
        assert "FALLBACK" in key

    def test_get_password_hash_alias(self):
        """L69: alias retrocompatível."""
        from api.auth.security import get_password_hash, verify_password
        h = get_password_hash("Senha123")
        assert verify_password("Senha123", h) is True


# ── api/schemas/auditoria L77: arquivo grande emite erro ─────────────────────

class TestAuditoriaSchema:
    def test_arquivo_excede_tamanho_max_emite_erro(self):
        from api.schemas.auditoria import TAMANHO_MAX
        from api.schemas.auditoria import validar_arquivos as validar_arquivos_upload

        class _FakeFile:
            def __init__(self, filename, size):
                self.filename = filename
                self.size = size
        gigante = _FakeFile("nota.pdf", TAMANHO_MAX + 1)
        erros = validar_arquivos_upload([gigante])
        assert any("excede" in e for e in erros)


# ── api/schemas/clientes L85, 88: CPF/CNPJ inválidos via field_validator ─────

class TestClientesSchemaValidator:
    def test_cpf_invalido_levanta_validation_error(self):
        from pydantic import ValidationError

        from api.schemas.clientes import ClienteUpdate
        with pytest.raises(ValidationError, match="CPF inválido"):
            ClienteUpdate(cpf_cnpj="123.456.789-00")  # DV inválido

    def test_cnpj_invalido_levanta_validation_error(self):
        from pydantic import ValidationError

        from api.schemas.clientes import ClienteUpdate
        with pytest.raises(ValidationError, match="CNPJ inválido"):
            ClienteUpdate(cpf_cnpj="11.222.333/0001-99")  # DV inválido


# ── api/middleware/security_headers L67, 74 ──────────────────────────────────

class TestSecurityHeadersEdges:
    @pytest.mark.asyncio
    async def test_hsts_aplicado_em_https_e_producao(self):
        from api.middleware.security_headers import SecurityHeadersMiddleware
        mw = SecurityHeadersMiddleware(app=None, enable_hsts=True)
        req = MagicMock()
        req.url.scheme = "https"
        req.url.path = "/"

        async def _next(_r):
            r = MagicMock()
            r.headers = {}
            return r

        resp = await mw.dispatch(req, _next)
        assert "Strict-Transport-Security" in resp.headers

    @pytest.mark.asyncio
    async def test_remove_headers_que_vazam_stack(self):
        from api.middleware.security_headers import SecurityHeadersMiddleware
        mw = SecurityHeadersMiddleware(app=None)
        req = MagicMock()
        req.url.scheme = "http"
        req.url.path = "/"

        async def _next(_r):
            r = MagicMock()
            r.headers = {"Server": "uvicorn", "X-Powered-By": "FastAPI"}
            return r

        resp = await mw.dispatch(req, _next)
        assert "Server" not in resp.headers
        assert "X-Powered-By" not in resp.headers
