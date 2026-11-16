"""Tools sistem: info agent, waktu, dan daftar tools."""
from __future__ import annotations

import datetime

from .. import __version__
from .registry import get_registry

reg = get_registry()


@reg.register(
    "get_time",
    "Dapatkan tanggal & waktu saat ini.",
    {"type": "object", "properties": {}},
)
def get_time(context: dict) -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


@reg.register(
    "list_tools",
    "Daftar semua tool yang tersedia untuk agent.",
    {"type": "object", "properties": {}},
)
def list_tools(context: dict) -> str:
    return ", ".join(get_registry().names())


@reg.register(
    "agent_info",
    "Tampilkan versi, provider, model, dan jumlah tools Laction Agent.",
    {"type": "object", "properties": {}},
)
def agent_info(context: dict) -> str:
    cfg = (context or {}).get("cfg")
    tools = get_registry().names()
    provider = getattr(cfg, "provider", "mock")
    model = getattr(cfg, "model", "mock-laction-1")
    return (
        f"Laction Agent v{__version__}\n"
        f"Provider: {provider}\n"
        f"Model: {model}\n"
        f"Tools: {len(tools)}\n"
        f"Daftar: {', '.join(tools)}"
    )
