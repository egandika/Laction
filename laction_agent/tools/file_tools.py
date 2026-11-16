"""Tools file: read, write, list, search. Dengan proteksi path traversal & workspace eksplisit."""
from __future__ import annotations

import os
from pathlib import Path

from .registry import get_registry

WORKSPACE = Path.cwd()
PROTECTED_FILENAMES = frozenset({"mcp_servers.json", "cron.json", "SKILL.md"})


def get_workspace(context: dict | None = None) -> Path:
    """Resolusi workspace aktif: Config.workspace > LACTION_WORKSPACE > WORKSPACE default."""
    cfg = (context or {}).get("cfg")
    cfg_ws = getattr(cfg, "workspace", "") if cfg is not None else ""
    if isinstance(cfg_ws, str) and cfg_ws.strip():
        return Path(cfg_ws.strip()).expanduser().resolve()
    env_ws = os.environ.get("LACTION_WORKSPACE", "").strip()
    if env_ws:
        return Path(env_ws).expanduser().resolve()
    return WORKSPACE.resolve()


def _safe(path: str, context: dict | None = None) -> Path:
    ws = get_workspace(context)
    p = (ws / path).resolve()
    # Cegah keluar dari workspace (../ dsb)
    if ws not in p.parents and p != ws:
        raise ValueError(f"Akses di luar workspace ditolak: {path}")
    return p


reg = get_registry()


@reg.register(
    "read_file",
    "Baca isi file teks. Pakai untuk melihat isi file sebelum mengubahnya.",
    {"type": "object", "properties": {"path": {"type": "string", "description": "Path file relatif ke workspace"}}, "required": ["path"]},
)
def read_file(path: str, context: dict) -> str:
    p = _safe(path, context)
    if not p.exists():
        return f"File tidak ditemukan: {path}"
    if p.is_dir():
        return f"{path} adalah direktori, bukan file."
    return p.read_text(encoding="utf-8", errors="replace")


@reg.register(
    "write_file",
    "Tulis / timpa isi file teks. Direktori induk dibuat otomatis.",
    {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]},
)
def write_file(path: str, content: str, context: dict) -> str:
    p = _safe(path, context)
    if p.name in PROTECTED_FILENAMES:
        return (
            f"DITOLAK: penulisan langsung ke '{p.name}' diblokir demi keamanan kontrol agent. "
            "Gunakan perintah/tool khusus yang melalui validasi & approval."
        )
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"Berhasil menulis {len(content)} karakter ke {path}"


@reg.register(
    "list_files",
    "Daftar isi direktori (default: workspace root).",
    {"type": "object", "properties": {"path": {"type": "string", "description": "Direktori, default '.'"}}},
)
def list_files(path: str = ".", context: dict | None = None) -> str:
    p = _safe(path or ".", context)
    if not p.exists():
        return f"Path tidak ditemukan: {path}"
    items = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
    lines = []
    for it in items:
        if it.name.startswith(".git"):
            continue
        lines.append(f"{'📄' if it.is_file() else '📁'} {it.name}")
    return "\n".join(lines) or "(kosong)"


@reg.register(
    "search_files",
    "Cari teks di semua file .py/.md/.txt dalam workspace (grep sederhana).",
    {"type": "object", "properties": {"query": {"type": "string"}, "ext": {"type": "string", "description": "Ekstensi, mis. .py — opsional"}}},
)
def search_files(query: str, ext: str = "", context: dict | None = None) -> str:
    ws = get_workspace(context)
    hits = []
    for p in ws.rglob("*"):
        if not p.is_file() or ".git" in p.parts or "__pycache__" in p.parts:
            continue
        if ext and p.suffix != ext:
            continue
        if p.suffix not in (".py", ".md", ".txt", ".yaml", ".toml", ".json"):
            continue
        try:
            resolved = p.resolve()
            if ws not in resolved.parents and resolved != ws:
                continue
            for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if query.lower() in line.lower():
                    hits.append(f"{resolved.relative_to(ws)}:{i}: {line.strip()[:120]}")
                    if len(hits) >= 50:
                        break
        except OSError:
            continue
    return "\n".join(hits) or f"Tidak ada hasil untuk: {query}"
