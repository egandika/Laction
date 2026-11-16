"""Utilitas kecil: path, logging, redaksi secret, dan helper teks."""
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


# Token umum: OpenAI, GitHub, Slack, Google, Anthropic-style.
_TOKEN_PATTERN = re.compile(
    r"(?i)\b(?:"
    r"sk-[A-Za-z0-9_\-]{8,}"
    r"|gh[pousr]_[A-Za-z0-9]{8,}"
    r"|github_pat_[A-Za-z0-9_]{10,}"
    r"|xox[baprs]-[A-Za-z0-9\-]{8,}"
    r"|AIza[0-9A-Za-z_\-]{20,}"
    r")"
)
_BEARER_PATTERN = re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9._\-]{8,}")
_KV_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|secret|password|token)"
    r"(\s*[:=]\s*)([\"']?)([^\s\"',}\]]{4,})"
)


def redact(text: str) -> str:
    """Samarkan kredensial sebelum ditulis ke log / SQLite.

    Menangani token berprefik (sk-, ghp_, github_pat_, xoxb-, AIza...),
    header Bearer, dan pasangan `api_key=...` / `"password": "..."`.
    Tidak boleh mengubah teks biasa.
    """
    if not text:
        return text
    out = str(text)
    out = _TOKEN_PATTERN.sub("***", out)
    out = _BEARER_PATTERN.sub(r"\1***", out)
    out = _KV_PATTERN.sub(lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}***", out)
    return out


def truncate(text: str, limit: int = 4000) -> str:
    """Potong dari depan (keep head), dengan penanda jumlah karakter."""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [terpotong, total {len(text)} karakter]"


def tail(text: str, limit: int) -> str:
    """Potong dari belakang (keep newest) — cocok untuk MEMORY.md yang append-only."""
    if len(text) <= limit:
        return text
    return f"[... {len(text) - limit} karakter lama dipotong ...]\n" + text[-limit:]
