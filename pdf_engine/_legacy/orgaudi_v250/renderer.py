"""
orgaudi_v250.renderer
═════════════════════
Renderizador HTML → PDF via Chrome headless (--print-to-pdf).

O Chrome já está instalado no sistema; não requer dependências extras.
Suporta CSS completo: gradientes, fontes customizadas, flexbox, grid,
@page rules para A4 e quebras de página.

Uso:
    from .renderer import html_para_pdf
    html_para_pdf(html_str, Path("saida.pdf"))
"""
from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger("orgaudi")

# Caminhos candidatos para o Chrome no Windows
_CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Users\{user}\AppData\Local\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files\Chromium\Application\chromium.exe",
]


def _encontrar_chrome() -> str | None:
    """Retorna o caminho para o executável Chrome/Chromium ou None."""
    import os
    for c in _CHROME_CANDIDATES:
        # Substituir {user} pelo usuário atual
        path = c.replace("{user}", os.environ.get("USERNAME", ""))
        if Path(path).exists():
            return path
    return None


def html_para_pdf(html: str, saida: Path, timeout: int = 60) -> None:
    """
    Converte uma string HTML completa em PDF via Chrome headless.

    Parâmetros
    ----------
    html    : string HTML completa (pode incluir CSS inline e fontes base64)
    saida   : caminho para o arquivo PDF de saída
    timeout : segundos máximos para o Chrome terminar (padrão 60s)

    Levanta
    -------
    RuntimeError se o Chrome não for encontrado ou falhar.
    """
    chrome = _encontrar_chrome()
    if not chrome:
        raise RuntimeError(
            "Chrome não encontrado. Instale o Google Chrome para usar o renderer v250."
        )

    saida = Path(saida)
    saida.parent.mkdir(parents=True, exist_ok=True)

    # Escreve HTML em arquivo temporário (Chrome precisa de URL file://)
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
            "--print-to-pdf-no-header",
            f"--print-to-pdf={saida.resolve()}",
            "--no-pdf-header-footer",
            tmp_path.resolve().as_uri(),
        ]
        logger.debug("Chrome cmd: %s", " ".join(str(c) for c in cmd))

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if result.returncode != 0:
            logger.warning("Chrome stderr: %s", result.stderr[:500])
            # Chrome headless às vezes retorna código != 0 mas gera o PDF
            if not saida.exists() or saida.stat().st_size < 1000:
                raise RuntimeError(
                    f"Chrome falhou (código {result.returncode}): {result.stderr[:200]}"
                )

        logger.info("PDF gerado: %s (%.1f KB)", saida.name, saida.stat().st_size / 1024)

    finally:
        try:
            tmp_path.unlink()
        except Exception:
            pass
