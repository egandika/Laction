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
    "Delegasikan satu tugas ke sub-agent read-only dengan sesi terpisah; bukan sandbox.",
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


@reg.register(
    "consult_team",
    "Konsultasikan 1–2 spesialis read-only secara paralel, lalu reviewer terpisah. Tidak menerapkan perubahan. Provider eksternal tetap menerima tugas/temuan.",
    {"type": "object", "properties": {
        "task": {"type": "string", "description": "Tugas dan konteks yang boleh dibagikan ke provider"},
        "roles": {"type": "array", "items": {"type": "string", "enum": ["apk", "research", "report"]}, "minItems": 1, "maxItems": 2},
    }, "required": ["task", "roles"]},
)
def consult_team(task: str, roles: list[str], context: dict | None = None) -> str:
    team = (context or {}).get("team")
    if team is None:
        return "DITOLAK: tim tidak tersedia di konteks ini."
    return team(task, roles)
