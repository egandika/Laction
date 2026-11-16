"""Utilitas kecil: path, logging, dan helper teks."""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("laction")


def get_home() -> Path:
    """Direktori data utama (profile). Default ./data, bisa override via LACTION_HOME."""
    home = os.environ.get("LACTION_HOME", "./data")
    p = Path(home).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return p


def redact(text: str) -> str:
    """Redaksi API key / token dari log agar tidak bocor."""
    return re.sub(r"(sk-[A-Za-z0-9_\-]{8,}|ghp_[A-Za-z0-9]{8,})", "***", text)


def truncate(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [terpotong, total {len(text)} karakter]"
