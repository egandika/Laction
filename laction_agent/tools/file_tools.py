"""Tools file: read, write, list, search. Dengan proteksi path traversal."""
from __future__ import annotations

from pathlib import Path

from .registry import get_registry

WORKSPACE = Path.cwd()


def _safe(path: str) -> Path:
    p = (WORKSPACE / path).resolve()
    # Cegah keluar dari workspace (../ dsb)
    if WORKSPACE.resolve() not in p.parents and p != WORKSPACE.resolve():
        raise ValueError(f"Akses di luar workspace ditolak: {path}")
    return p


reg = get_registry()


@reg.register(
    "read_file",
    "Baca isi file teks. Pakai untuk melihat isi file sebelum mengubahnya.",
    {"type": "object", "properties": {"path": {"type": "string", "description": "Path file relatif ke workspace"}}, "required": ["path"]},
)
def read_file(path: str, context: dict) -> str:
    p = _safe(path)
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
    p = _safe(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"Berhasil menulis {len(content)} karakter ke {path}"


@reg.register(
    "list_files",
    "Daftar isi direktori (default: workspace root).",
    {"type": "object", "properties": {"path": {"type": "string", "description": "Direktori, default '.'"}}},
)
def list_files(path: str = ".", context: dict = None) -> str:
    p = _safe(path or ".")
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
def search_files(query: str, ext: str = "", context: dict = None) -> str:
    hits = []
    for p in WORKSPACE.rglob("*"):
        if not p.is_file() or ".git" in p.parts or "__pycache__" in p.parts:
            continue
        if ext and p.suffix != ext:
            continue
        if p.suffix not in (".py", ".md", ".txt", ".yaml", ".toml", ".json"):
            continue
        try:
            for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if query.lower() in line.lower():
                    hits.append(f"{p.relative_to(WORKSPACE)}:{i}: {line.strip()[:120]}")
                    if len(hits) >= 50:
                        break
        except OSError:
            continue
    return "\n".join(hits) or f"Tidak ada hasil untuk: {query}"
