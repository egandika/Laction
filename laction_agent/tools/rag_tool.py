"""Local lexical RAG over workspace text files (stdlib-only BM25, no embeddings)."""
from __future__ import annotations

import math
import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from ..utils import redact
from . import file_tools
from .registry import get_registry

TEXT_SUFFIXES = {
    ".py", ".md", ".txt", ".rst", ".json", ".yaml", ".yml", ".toml",
    ".ini", ".cfg", ".csv", ".html", ".htm", ".js", ".ts", ".tsx",
    ".jsx", ".css", ".sql", ".sh", ".xml",
}
SKIP_PARTS = {
    ".git", ".hg", ".svn", ".venv", "venv", "node_modules", "__pycache__",
    ".cache", "data", "build", "dist", "coverage", "target", "out",
}
MAX_FILES = 300
MAX_FILE_BYTES = 512 * 1024
MAX_TOTAL_BYTES = 8 * 1024 * 1024
MAX_CHUNKS = 2500
CHUNK_CHARS = 1600
CHUNK_LINES = 35
_TOKEN_RE = re.compile(r"[\w]{2,}", re.UNICODE)
_STOPWORDS = set("""
 a an and are as at be by for from has have in is it its of on or that the this to was were with
 apa atau dan dari dalam dengan di ke karena oleh pada saat sebagai tentang untuk yang saya kamu ini itu
""".split())

reg = get_registry()


@dataclass(frozen=True)
class _Chunk:
    path: str
    start_line: int
    end_line: int
    text: str
    terms: Counter


def _tokens(text: str) -> list[str]:
    return [term.casefold() for term in _TOKEN_RE.findall(text) if term.casefold() not in _STOPWORDS]


def _iter_files(root: Path):
    workspace = file_tools.WORKSPACE.resolve()

    def acceptable(path: Path) -> bool:
        try:
            if path.is_symlink() or not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
                return False
            resolved = path.resolve()
            if resolved != workspace and workspace not in resolved.parents:
                return False
            relative = resolved.relative_to(workspace)
            if any(part.startswith(".") or part.lower() in SKIP_PARTS for part in relative.parts):
                return False
            return path.stat().st_size <= MAX_FILE_BYTES
        except OSError:
            return False

    count = 0
    if root.is_file():
        if acceptable(root):
            yield root
        return

    # Prune hidden, sensitive, cache and build directories before descending.
    for current, dirs, filenames in os.walk(root, followlinks=False):
        dirs[:] = [
            name for name in dirs
            if not name.startswith(".")
            and name.lower() not in SKIP_PARTS
            and not (Path(current) / name).is_symlink()
        ]
        for name in filenames:
            path = Path(current) / name
            if not acceptable(path):
                continue
            yield path
            count += 1
            if count >= MAX_FILES:
                return


def _split_file(path: Path, text: str) -> list[tuple[int, int, str]]:
    lines = text.splitlines()
    chunks: list[tuple[int, int, str]] = []
    group: list[str] = []
    start = 1
    chars = 0
    for line_no, line in enumerate(lines, 1):
        extra = len(line) + (1 if group else 0)
        if group and (chars + extra > CHUNK_CHARS or len(group) >= CHUNK_LINES):
            chunks.append((start, line_no - 1, "\n".join(group)))
            group, chars, start = [], 0, line_no
        if not group:
            start = line_no
        group.append(line)
        chars += len(line) + (1 if len(group) > 1 else 0)
    if group:
        chunks.append((start, len(lines), "\n".join(group)))
    return chunks


def _collect(root: Path) -> tuple[list[_Chunk], bool]:
    chunks: list[_Chunk] = []
    total_bytes = 0
    limited = False
    workspace = file_tools.WORKSPACE.resolve()
    for path in _iter_files(root):
        try:
            size = path.stat().st_size
            if total_bytes + size > MAX_TOTAL_BYTES:
                limited = True
                break
            text = path.read_text(encoding="utf-8", errors="replace")
            total_bytes += size
            rel = str(path.resolve().relative_to(workspace))
        except (OSError, ValueError):
            continue
        for start, end, content in _split_file(path, text):
            terms = Counter(_tokens(content))
            if not terms:
                continue
            chunks.append(_Chunk(rel, start, end, content, terms))
            if len(chunks) >= MAX_CHUNKS:
                limited = True
                return chunks, limited
    return chunks, limited


def _bm25(chunks: list[_Chunk], query_terms: list[str]) -> list[tuple[float, _Chunk]]:
    if not chunks or not query_terms:
        return []
    doc_freq: Counter = Counter()
    for chunk in chunks:
        doc_freq.update(chunk.terms.keys())
    avg_len = sum(sum(chunk.terms.values()) for chunk in chunks) / len(chunks) or 1.0
    total = len(chunks)
    scored: list[tuple[float, _Chunk]] = []
    for chunk in chunks:
        length = sum(chunk.terms.values())
        score = 0.0
        for term in query_terms:
            tf = chunk.terms.get(term, 0)
            if not tf:
                continue
            df = doc_freq[term]
            idf = math.log(1.0 + (total - df + 0.5) / (df + 0.5))
            score += idf * (tf * 2.5) / (tf + 1.5 * (0.25 + 0.75 * length / avg_len))
        if score > 0:
            scored.append((score, chunk))
    return sorted(scored, key=lambda pair: (-pair[0], pair[1].path, pair[1].start_line))


@reg.register(
    "rag_search",
    "Cari potongan relevan di file teks workspace memakai BM25 lokal; hasil menyertakan path dan baris. Bukan vector/embedding search.",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Pertanyaan atau kata kunci"},
            "path": {"type": "string", "description": "Folder/file relatif di workspace, default '.'"},
            "limit": {"type": "integer", "description": "Jumlah hasil 1-10 (default 5)", "minimum": 1, "maximum": 10},
        },
        "required": ["query"],
    },
)
def rag_search(query: str, path: str = ".", limit: int = 5, context: dict | None = None) -> str:
    query = (query or "").strip()
    if not query:
        return "Query tidak boleh kosong."
    if len(query) > 500:
        return "Query dibatasi 500 karakter."
    terms = list(dict.fromkeys(_tokens(query)))
    if not terms:
        return "Query tidak memiliki kata yang dapat dicari."
    try:
        root = file_tools._safe(path or ".")
    except ValueError as exc:
        return f"DITOLAK: {exc}"
    if not root.exists() or not (root.is_dir() or root.is_file()):
        return f"Path tidak ditemukan: {path}"
    try:
        relative_root = root.resolve().relative_to(file_tools.WORKSPACE.resolve())
    except ValueError:
        return f"DITOLAK: path keluar dari workspace: {path}"
    if any(part.startswith(".") or part.lower() in SKIP_PARTS for part in relative_root.parts):
        return f"Path dikecualikan dari retrieval lokal: {path}"
    chunks, limited = _collect(root)
    results = _bm25(chunks, terms)[: min(max(int(limit), 1), 10)]
    if not results:
        return f"Tidak ada potongan lokal yang cocok untuk: {query}"
    lines = ["Local RAG (BM25 leksikal; bukan vector/embedding search):"]
    for i, (score, chunk) in enumerate(results, 1):
        lines.append(f"\n[{i}] {chunk.path}:{chunk.start_line}-{chunk.end_line} (score {score:.2f})")
        lines.append(redact(chunk.text))
    if limited:
        lines.append("\nCatatan: indeks dibatasi oleh batas ukuran/jumlah file; hasil mungkin tidak mencakup seluruh workspace.")
    return "\n".join(lines)
