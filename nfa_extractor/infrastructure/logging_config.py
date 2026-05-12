"""
ORGATEC — Configuração de logging estruturado.

Uso:
    from nfa_extractor.infrastructure.logging_config import setup_logging, get_logger

    setup_logging()  # Chamar 1x no startup
    logger = get_logger(__name__)
    logger.info("mensagem", extra={"contexto": "valor"})
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

LOG_FORMAT = "%(asctime)s | %(levelname)-5s | %(name)s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FILE = os.getenv("LOG_FILE", "extractor.log")
LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", "10485760"))  # 10MB
LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "5"))


def setup_logging() -> None:
    """Configura logging com output em console + arquivo rotativo."""
    root = logging.getLogger()
    root.setLevel(LOG_LEVEL)

    # Limpa handlers existentes para evitar duplicação
    root.handlers.clear()

    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    root.addHandler(console)

    # Arquivo rotativo
    try:
        file_handler = RotatingFileHandler(
            LOG_FILE,
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError:
        root.warning(f"Não foi possível criar log em {LOG_FILE}. Apenas console.")

    # Silenciar loggers barulhentos de terceiros
    for noisy in ("httpcore", "httpx", "urllib3", "matplotlib"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Retorna logger nomeado."""
    return logging.getLogger(name)
