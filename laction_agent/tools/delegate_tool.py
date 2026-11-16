"""
Tool delegasi: spawn sub-agent dengan konteks terisolasi.

Mirip Hermes delegate_task — sub-agent dapat percakapan & toolset
sendiri, jadi context window agent utama tidak tercemar.
"""
from __future__ import annotations

from ..team import MAX_TEAM_TIMEOUT, MIN_TEAM_TIMEOUT
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
    "Konsultasikan 1–2 spesialis read-only atau debat 1 putaran (pro/contra) secara paralel, lalu reviewer terpisah. Tidak menerapkan perubahan; provider eksternal tetap menerima tugas/temuan.",
    {"type": "object", "properties": {
        "task": {"type": "string", "description": "Tugas dan konteks yang boleh dibagikan ke provider"},
        "roles": {"type": "array", "items": {"type": "string", "enum": ["apk", "research", "report"]}, "minItems": 1, "maxItems": 2, "description": "Dipakai pada mode='specialists' (default ['research', 'report'])."},
        "mode": {"type": "string", "enum": ["specialists", "debate"], "description": "specialists (default) atau debate (1 putaran Pro vs Contra + reviewer)."},
        "timeout_seconds": {
            "type": "integer",
            "description": f"Batas wall-clock total tim dalam detik ({MIN_TEAM_TIMEOUT}–{MAX_TEAM_TIMEOUT}); default dari LACTION_TEAM_TIMEOUT.",
            "minimum": MIN_TEAM_TIMEOUT,
            "maximum": MAX_TEAM_TIMEOUT,
        },
    }, "required": ["task"]},
)
def consult_team(
    task: str,
    roles: list[str] | None = None,
    mode: str = "specialists",
    context: dict | None = None,
    timeout_seconds: int | None = None,
) -> str:
    team = (context or {}).get("team")
    if team is None:
        return "DITOLAK: tim tidak tersedia di konteks ini."
    return team(task, roles, mode=mode, timeout_seconds=timeout_seconds)
