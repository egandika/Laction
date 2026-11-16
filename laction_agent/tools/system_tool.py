"""Tools sistem: info agent, waktu, dan daftar tools."""
from __future__ import annotations

import datetime
import shutil
from pathlib import Path

from .. import __version__
from . import file_tools
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
    allowed = (context or {}).get("allowed_tools")
    return ", ".join(t["name"] for t in get_registry().schemas(allowed))


@reg.register(
    "agent_info",
    "Tampilkan versi, provider, model, dan jumlah tools Laction Agent.",
    {"type": "object", "properties": {}},
)
def agent_info(context: dict) -> str:
    cfg = (context or {}).get("cfg")
    allowed = (context or {}).get("allowed_tools")
    tools = [t["name"] for t in get_registry().schemas(allowed)]
    provider = getattr(cfg, "provider", "mock")
    model = getattr(cfg, "model", "mock-laction-1")
    sandbox = getattr(cfg, "sandbox_mode", "none")
    return (
        f"Laction Agent v{__version__}\n"
        f"Provider: {provider}\n"
        f"Model: {model}\n"
        f"Sandbox: {sandbox}\n"
        f"Tools: {len(tools)}\n"
        f"Daftar: {', '.join(tools)}"
    )


@reg.register(
    "device_health",
    "Baca ringkasan RAM dan storage saja; tidak membersihkan atau mengubah perangkat.",
    {"type": "object", "properties": {}},
)
def device_health(context: dict | None = None) -> str:
    ws = file_tools.get_workspace(context)
    disk = shutil.disk_usage(ws if ws.exists() else Path.cwd())
    lines = [f"Storage workspace: total={disk.total} byte, tersedia={disk.free} byte"]
    try:
        values = {}
        for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
            key, _, value = line.partition(":")
            if key in {"MemTotal", "MemAvailable"}:
                values[key] = value.strip()
        lines.append(f"RAM: total={values.get('MemTotal', 'tidak tersedia')}, tersedia={values.get('MemAvailable', 'tidak tersedia')}")
    except OSError:
        lines.append("RAM: tidak tersedia pada sistem ini")
    return "\n".join(lines)
