"""Tools memory: MEMORY.md / USER.md (Tier 1) + pencarian sesi FTS5 (Tier 2)."""
from __future__ import annotations

import json

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
    raw = " ".join(str(note or "").splitlines()).strip()
    clean = mgr.append_memory(raw)
    if not clean:
        return "ERROR: catatan tidak boleh kosong."
    suffix = " [kredensial disamarkan]" if clean != raw or redact(note) != note else ""
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
    raw = " ".join(str(note or "").splitlines()).strip()
    clean = mgr.append_user(raw)
    if not clean:
        return "ERROR: catatan tidak boleh kosong."
    suffix = " [kredensial disamarkan]" if clean != raw or redact(note) != note else ""
    return f"Tersimpan ke USER.md: {clean}{suffix}"


@reg.register(
    "memory_search",
    "Cari kata kunci di riwayat sesi SQLite memakai FTS5 (BM25) + fallback LIKE.",
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


@reg.register(
    "memory_prune",
    "Pangkas dan deduplikasi catatan lama di MEMORY.md / USER.md sambil mempertahankan catatan terbaru.",
    {
        "type": "object",
        "properties": {
            "max_entries": {
                "type": "integer",
                "description": "Maksimum jumlah entri terbaru per file (default 50)",
                "minimum": 1,
                "maximum": 500,
            },
            "max_chars": {
                "type": "integer",
                "description": "Maksimum karakter per file (default 6000)",
                "minimum": 256,
                "maximum": 32000,
            },
            "target": {
                "type": "string",
                "description": "all | memory | user (default all)",
                "enum": ["all", "memory", "user"],
            },
        },
    },
)
def memory_prune(
    max_entries: int = 50,
    max_chars: int = 6000,
    target: str = "all",
    context: dict | None = None,
) -> str:
    mgr = (context or {}).get("memory")
    if mgr is None:
        return "Memory manager tidak tersedia."
    try:
        stats = mgr.prune(max_entries=max_entries, max_chars=max_chars, target=target)
    except ValueError as exc:
        return f"ERROR: {exc}"
    return f"Memory dipangkas: {json.dumps(stats, ensure_ascii=False)}"
