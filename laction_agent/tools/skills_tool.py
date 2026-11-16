"""Tools skills: list, view, create SKILL.md (procedural memory)."""
from __future__ import annotations

from ..utils import redact
from .registry import get_registry

reg = get_registry()


@reg.register(
    "list_skills",
    "Daftar semua skill yang tersedia (bawaan + buatan agent).",
    {"type": "object", "properties": {}},
)
def list_skills(context: dict) -> str:
    mgr = (context or {}).get("skills")
    if mgr is None:
        return "Skill manager tidak tersedia."
    skills = mgr.list_skills()
    if not skills:
        return "(belum ada skill)"
    return "\n".join(f"- {s['name']}: {s['description']}" for s in skills)


@reg.register(
    "view_skill",
    "Lihat isi lengkap satu skill.",
    {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
)
def view_skill(name: str, context: dict) -> str:
    mgr = (context or {}).get("skills")
    if mgr is None:
        return "Skill manager tidak tersedia."
    content = mgr.view_skill(name)
    return content or f"Skill tidak ditemukan: {name}"


@reg.register(
    "create_skill",
    "Buat skill baru dari pengalaman (self-improving loop). Isi = langkah-langkah prosedural.",
    {"type": "object", "properties": {"name": {"type": "string", "description": "Nama skill, huruf kecil + strip"}, "content": {"type": "string", "description": "Langkah-langkah / prosedur skill"}}, "required": ["name", "content"]},
)
def create_skill(name: str, content: str, context: dict) -> str:
    mgr = (context or {}).get("skills")
    if mgr is None:
        return "Skill manager tidak tersedia."
    try:
        path = mgr.create_skill(name, redact(content))
        return f"Skill '{name}' dibuat di {path}"
    except Exception as e:  # noqa: BLE001
        return f"ERROR membuat skill: {e}"
