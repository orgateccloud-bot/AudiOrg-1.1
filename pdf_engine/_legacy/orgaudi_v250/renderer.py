"""orgaudi.renderer — HTML → PDF cross-platform.

Renderiza HTML para PDF usando Chrome/Chromium headless em qualquer SO
(Windows, macOS, Linux). Em produção Kubernetes, recomenda-se rodar com
\`chromium\` instalado via pacote (apt-get install chromium / chromium-browser).

Estratégia de busca do navegador:
1. Variável de ambiente CHROME_BIN (override explícito)
2. shutil.which() em PATH (chrome, chromium, google-chrome, msedge)
3. Caminhos conhecidos por SO (Program Files, /Applications, /usr/bin)

Fallback opcional (não-bloqueante): se WeasyPrint estiver instalado e o
Chrome não for encontrado, usa WeasyPrint. Não levanta erro de import se
faltar — apenas registra warning.

Uso:

    from orgaudi.renderer import html_para_pdf
    html_para_pdf(html_str, Path("saida.pdf"))
"""
from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("orgaudi")

# Métricas Prometheus opcionais
try:
    from horizon_blue_one.core.metrics import PDF_BUILDS, PDF_BUILD_LATENCY
    _METRICAS = True
except ImportError:
    _METRICAS = False


# Resolução cross-platform do navegador

_CANDIDATOS_PATH = (
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "chrome",
    "msedge",
)

_CANDIDATOS_WINDOWS = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files\Chromium\Application\chromium.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
)

_CANDIDATOS_MACOS = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
)

_CANDIDATOS_LINUX = (
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/snap/bin/chromium",
)


def _encontrar_chrome():
    """Retorna o caminho do executável Chrome/Chromium/Edge ou None."""
    env_bin = os.environ.get("CHROME_BIN", "").strip()
    if env_bin and Path(env_bin).exists():
        return env_bin

    for cmd in _CANDIDATOS_PATH:
        path = shutil.which(cmd)
        if path:
            return path

    sistema = platform.system()
    if sistema == "Windows":
        candidatos = list(_CANDIDATOS_WINDOWS) + [
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ]
    elif sistema == "Darwin":
        candidatos = _CANDIDATOS_MACOS
    else:
        candidatos = _CANDIDATOS_LINUX

    for c in candidatos:
        if Path(c).exists():
            return c
    return None


def _tentar_weasyprint(html, saida):
    """Tenta renderizar via WeasyPrint. Retorna True se conseguiu."""
    try:
        from weasyprint import HTML  # type: ignore
    except ImportError:
        return False
    try:
        HTML(string=html).write_pdf(target=str(saida))
        logger.info("PDF gerado via WeasyPrint: %s", saida.name)
        return True
    except Exception as exc:
        logger.warning("weasyprint_falhou erro=%s", exc)
        return False


def html_para_pdf(html, saida, timeout=60):
    """Converte uma string HTML completa em PDF.

    Estratégia:
    1. Chrome/Chromium headless (preferido).
    2. WeasyPrint (fallback se instalado).
    3. RuntimeError se nenhum disponível.
    """
    inicio = time.monotonic()
    saida = Path(saida)
    saida.parent.mkdir(parents=True, exist_ok=True)

    chrome = _encontrar_chrome()
    if chrome:
        try:
            _renderizar_chrome(chrome, html, saida, timeout)
            _registrar_metrica("ok", time.monotonic() - inicio)
            return
        except Exception as exc:
            logger.warning("chrome_falhou_tentando_weasyprint erro=%s", exc)

    if _tentar_weasyprint(html, saida):
        _registrar_metrica("weasyprint", time.monotonic() - inicio)
        return

    _registrar_metrica("erro", time.monotonic() - inicio)
    raise RuntimeError(
        "Nenhum renderizador disponivel. Instale Chrome/Chromium ou WeasyPrint."
    )


def _renderizar_chrome(chrome, html, saida, timeout):
    """Executa Chrome headless --print-to-pdf."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".html", encoding="utf-8", delete=False
    ) as tmp:
        tmp.write(html)
        tmp_path = Path(tmp.name)

    try:
        cmd = [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-extensions",
            "--run-all-compositor-stages-before-draw",
            "--no-pdf-header-footer",
            "--print-to-pdf=" + str(saida.resolve()),
            tmp_path.resolve().as_uri(),
        ]
        logger.debug("chrome_cmd %s", " ".join(str(c) for c in cmd))

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )

        if result.returncode != 0:
            logger.warning("chrome_stderr %s", result.stderr[:500])
            if not saida.exists() or saida.stat().st_size < 1000:
                raise RuntimeError(
                    "Chrome falhou (codigo " + str(result.returncode) + "): "
                    + result.stderr[:200]
                )

        logger.info(
            "PDF gerado via Chrome: %s (%.1f KB)",
            saida.name,
            saida.stat().st_size / 1024,
        )
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass


def _registrar_metrica(status, latencia_s):
    if _METRICAS:
        try:
            PDF_BUILDS.labels(status=status).inc()
            PDF_BUILD_LATENCY.observe(latencia_s)
        except Exception:
            pass


__all__ = ["html_para_pdf"]
