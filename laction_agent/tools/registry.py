"""
Tool Registry — pusat pendaftaran & dispatch tool.

Mirip Hermes: tools self-register via decorator @register,
lalu agent hanya perlu tahu nama + skema JSON-nya.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

from ..utils import log, truncate


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    handler: Callable[..., str]
    dangerous: bool = False


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, name: str, description: str, parameters: dict, dangerous: bool = False):
        def deco(fn: Callable[..., str]):
            self._tools[name] = Tool(name, description, parameters, fn, dangerous)
            log.debug("Tool terdaftar: %s", name)
            return fn
        return deco

    def schemas(self, allowed_tools: frozenset[str] | None = None) -> list[dict]:
        return [
            {"name": t.name, "description": t.description, "parameters": t.parameters}
            for t in self._tools.values() if allowed_tools is None or t.name in allowed_tools
        ]

    def names(self) -> list[str]:
        return sorted(self._tools)

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def call(self, name: str, arguments: dict, context: dict | None = None) -> str:
        allowed = (context or {}).get("allowed_tools")
        if allowed is not None and name not in allowed:
            return f"DITOLAK: tool {name} tidak diizinkan dalam konteks terbatas."
        tool = self._tools.get(name)
        if tool is None:
            return json.dumps({"error": f"Tool tidak dikenal: {name}", "available": self.names()})
        try:
            result = tool.handler(context=_with_defaults(context), **(arguments or {}))
            return truncate(str(result), 8000)
        except Exception as e:  # noqa: BLE001 — tool error harus jadi string, bukan crash agent
            log.exception("Tool %s gagal", name)
            return json.dumps({"error": str(e), "tool": name})


# Tool yang membaca/menulis path relatif dan karena itu butuh workspace eksplisit.
_DEFAULT_KEYS = ("workspace", "sandbox_mode", "approval_mode", "home")


def _with_defaults(context: dict | None) -> dict:
    """Lengkapi konteks yang hilang dari env, tanpa melonggarkan guard.

    Panggilan langsung `registry.call(...)` (CLI non-interaktif, gateway, test,
    cron lama) sebelumnya jatuh ke default modul seperti `Path.cwd()` saat import
    dan `approval_mode` hardcoded. Di sini nilai env/normatif diisi supaya
    `LACTION_WORKSPACE`/`LACTION_SANDBOX_MODE`/`LACTION_APPROVAL_MODE` ikut
    berlaku. `approve` sengaja TIDAK diisi: tanpa callback, tool berisiko tetap
    fail-closed (`PERLU APPROVAL`).
    """
    import os
    from pathlib import Path

    ctx = dict(context or {})
    if "cfg" in ctx and ctx["cfg"] is not None:
        cfg = ctx["cfg"]
        for key, attr in (
            ("workspace", "workspace"),
            ("sandbox_mode", "sandbox_mode"),
            ("approval_mode", "approval_mode"),
            ("home", "home"),
        ):
            if not ctx.get(key):
                value = getattr(cfg, attr, None)
                if value:
                    ctx[key] = value
    ctx.setdefault("workspace", os.environ.get("LACTION_WORKSPACE", "").strip())
    ctx.setdefault("sandbox_mode", os.environ.get("LACTION_SANDBOX_MODE", "none").strip() or "none")
    ctx.setdefault("approval_mode", os.environ.get("LACTION_APPROVAL_MODE", "smart").strip() or "smart")
    ctx.setdefault("home", os.environ.get("LACTION_HOME", "./data"))
    if not ctx.get("workspace"):
        ctx["workspace"] = str(Path.cwd())
    return ctx



_registry: ToolRegistry | None = None


def get_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        # Import di sini supaya tool mendaftar sendiri (hindari circular import)
        from . import simulation_tool, apk_tools, cron_tool, delegate_tool, file_tools, mcp_tool, memory_tool, python_tool, rag_tool, search_tool, skills_tool, system_tool, terminal_tool, web_tools  # noqa: F401
    return _registry
