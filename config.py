"""Konfiguration und Logging für YouTube Video Manager."""

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# .env Datei laden (aus Projektverzeichnis)
PROJECT_ROOT = Path(__file__).parent
load_dotenv(PROJECT_ROOT / ".env")

# Pfade
DATA_DIR = PROJECT_ROOT / "data"
THUMBNAILS_DIR = PROJECT_ROOT / "thumbnails"
OUTPUT_DIR = PROJECT_ROOT / "output"


def setup_logging(level: int = logging.INFO) -> None:
    """Richtet das Logging fuer die gesamte Anwendung ein."""
    log_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    logging.basicConfig(
        level=level,
        format=log_format,
        datefmt=date_format,
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # Externe Libraries leiser stellen
    for lib in ("httpx", "httpcore", "urllib3", "yt_dlp"):
        logging.getLogger(lib).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Erstellt einen Logger mit dem angegebenen Namen."""
    return logging.getLogger(name)


def get_api_key() -> str | None:
    """Gibt den Anthropic API-Key zurueck (aus .env oder Umgebung)."""
    return os.getenv("ANTHROPIC_API_KEY")
