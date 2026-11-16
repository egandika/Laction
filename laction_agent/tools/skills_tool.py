"""Tools skills: list, view, create SKILL.md (procedural memory)."""
from __future__ import annotations

from ..utils import redact
from .python_tool import _approval_display
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
    if not isinstance(name, str) or not isinstance(content, str) or not content.strip() or len(content) > 10000:
        return "ERROR: nama dan isi skill wajib ada; isi maksimal 10000 karakter."
    import re
    normalized = re.sub(r"[^a-z0-9\-]+", "-", name.lower()).strip("-")
    if not normalized or len(normalized) > 64:
        return "ERROR: nama skill tidak valid."
    if any(s["name"] == normalized for s in mgr.list_skills()):
        return "DITOLAK: skill sudah ada; tidak boleh menimpa skill yang ada."
    safe_content = redact(content)
    approve = (context or {}).get("approve")
    if (context or {}).get("approval_mode") == "never" or approve is None:
        return "PERLU APPROVAL: skill belum dibuat; tinjau isi melalui chat interaktif."
    try:
        if not approve(f"Buat skill {normalized} (instruksi persisten; bukan kode):\n{_approval_display(safe_content)}"):
            return "DITOLAK: skill belum dibuat."
        # Check again after approval to avoid silently overwriting a skill.
        if any(s["name"] == normalized for s in mgr.list_skills()):
            return "DITOLAK: skill sudah ada."
        path = mgr.create_skill(normalized, safe_content)
        return f"Skill '{normalized}' dibuat di {path}. Ini prosedur, bukan kode teruji atau pembelajaran model."
    except Exception as e:  # noqa: BLE001
        return f"ERROR membuat skill: {e}"
