"""Tools memory: MEMORY.md / USER.md (Tier 1) + pencarian sesi (Tier 2)."""
from __future__ import annotations

from ..utils import redact, truncate
from .registry import get_registry

reg = get_registry()


@reg.register(
    "memory_save",
    "Simpan catatan penting ke MEMORY.md agar diingat antar sesi.",
    {"type": "object", "properties": {"note": {"type": "string"}}, "required": ["note"]},
)
def memory_save(note: str, context: dict) -> str:
    mgr = (context or {}).get("memory")
    if mgr is None:
        return "Memory manager tidak tersedia."
    clean = redact(note)  # MEMORY.md selalu masuk system prompt → jangan bawa secret
    mgr.append_memory(clean)
    suffix = " [kredensial disamarkan]" if clean != note else ""
    return f"Tersimpan ke MEMORY.md: {clean}{suffix}"


@reg.register(
    "memory_read",
    "Baca MEMORY.md + USER.md saat ini.",
    {"type": "object", "properties": {}},
)
def memory_read(context: dict) -> str:
    mgr = (context or {}).get("memory")
    if mgr is None:
        return "Memory manager tidak tersedia."
    return mgr.read_all() or "(memory masih kosong)"


@reg.register(
    "user_save",
    "Simpan preferensi user ke USER.md (mis. nama, gaya kerja, proyek).",
    {"type": "object", "properties": {"note": {"type": "string"}}, "required": ["note"]},
)
def user_save(note: str, context: dict) -> str:
    mgr = (context or {}).get("memory")
    if mgr is None:
        return "Memory manager tidak tersedia."
    clean = redact(note)
    mgr.append_user(clean)
    suffix = " [kredensial disamarkan]" if clean != note else ""
    return f"Tersimpan ke USER.md: {clean}{suffix}"


@reg.register(
    "memory_search",
    "Cari kata kunci di riwayat sesi SQLite (pesan + hasil tool lampau).",
    {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
)
def memory_search(query: str, context: dict) -> str:
    db = (context or {}).get("db")
    if db is None:
        return "Session DB tidak tersedia."
    rows = db.search(query, limit=10)
    if not rows:
        return f"Tidak ada riwayat yang cocok dengan: {query}"
    return "\n".join(
        f"[{r['created_at']}] ({r['session_id']}) {r['role']}: {truncate(r['content'], 240)}"
        for r in rows
    )
