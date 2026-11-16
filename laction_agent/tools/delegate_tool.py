"""
Tool delegasi: spawn sub-agent dengan konteks terisolasi.

Mirip Hermes delegate_task — sub-agent dapat percakapan & toolset
sendiri, jadi context window agent utama tidak tercemar.
"""
from __future__ import annotations

from .registry import get_registry

reg = get_registry()


@reg.register(
    "delegate_task",
    "Delegasikan tugas ke sub-agent terisolasi (cocok untuk kerja paralel / riset terpisah).",
    {"type": "object", "properties": {"task": {"type": "string"}}, "required": ["task"]},
)
def delegate_task(task: str, context: dict) -> str:
    delegate = (context or {}).get("delegate")
    if delegate is None:
        return "Delegasi tidak tersedia di konteks ini."
    try:
        return delegate(task)
    except Exception as e:  # noqa: BLE001
        return f"ERROR delegasi: {e}"
