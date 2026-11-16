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
            result = tool.handler(context=context or {}, **(arguments or {}))
            return truncate(str(result), 8000)
        except Exception as e:  # noqa: BLE001 — tool error harus jadi string, bukan crash agent
            log.exception("Tool %s gagal", name)
            return json.dumps({"error": str(e), "tool": name})


_registry: ToolRegistry | None = None


def get_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        # Import di sini supaya tool mendaftar sendiri (hindari circular import)
        from . import simulation_tool, apk_tools, cron_tool, delegate_tool, file_tools, mcp_tool, memory_tool, python_tool, rag_tool, search_tool, skills_tool, system_tool, terminal_tool, web_tools  # noqa: F401
    return _registry
