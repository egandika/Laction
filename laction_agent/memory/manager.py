"""
Memory Manager — Tier 1 Hermes-style: MEMORY.md + USER.md.

Kedua file dimuat ke system prompt setiap sesi (nol latensi retrieval).
Seluruh penulisan melewati redaksi kredensial terpusat dan batas ukuran disk,
serta mendukung pemangkasan (`prune`) terstruktur.
"""
from __future__ import annotations

import datetime
import re
from pathlib import Path

from ..utils import redact

MEMORY_HEADER = "# MEMORY.md — Ingatan jangka panjang Laction Agent"
USER_HEADER = "# USER.md — Profil & preferensi user"
MAX_MEMORY_FILE_CHARS = 32_000
_STAMP_PREFIX_RE = re.compile(r"^-\s*\[\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}\]\s*(.+)$")


class MemoryManager:
    def __init__(self, home: Path, max_file_chars: int = MAX_MEMORY_FILE_CHARS):
        self.home = Path(home)
        self.home.mkdir(parents=True, exist_ok=True)
        self.max_file_chars = max(512, int(max_file_chars))
        self.memory_file = self.home / "MEMORY.md"
        self.user_file = self.home / "USER.md"
        self._ensure()

    def _ensure(self):
        if not self.memory_file.exists():
            self.memory_file.write_text(f"{MEMORY_HEADER}\n\n", encoding="utf-8")
        if not self.user_file.exists():
            self.user_file.write_text(f"{USER_HEADER}\n\n", encoding="utf-8")

    def read_memory(self) -> str:
        return self.memory_file.read_text(encoding="utf-8").strip()

    def read_user(self) -> str:
        return self.user_file.read_text(encoding="utf-8").strip()

    def read_all(self) -> str:
        return f"--- MEMORY.md ---\n{self.read_memory()}\n\n--- USER.md ---\n{self.read_user()}"

    @staticmethod
    def _clean_note(note: str) -> str:
        cleaned = " ".join(redact(str(note or "")).splitlines()).strip()
        return cleaned

    def _append(self, path: Path, default_header: str, note: str) -> str:
        clean = self._clean_note(note)
        if not clean:
            return ""
        stamp = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
        with path.open("a", encoding="utf-8") as f:
            f.write(f"- [{stamp}] {clean}\n")
        if path.stat().st_size > self.max_file_chars:
            self._prune_file(path, default_header, max_entries=200, max_chars=self.max_file_chars)
        return clean

    def append_memory(self, note: str) -> str:
        return self._append(self.memory_file, MEMORY_HEADER, note)

    def append_user(self, note: str) -> str:
        return self._append(self.user_file, USER_HEADER, note)

    @staticmethod
    def _entry_key(line: str) -> str:
        match = _STAMP_PREFIX_RE.match(line.strip())
        if match:
            return match.group(1).strip()
        return line.strip()

    @classmethod
    def _prune_file(
        cls,
        path: Path,
        default_header: str,
        max_entries: int,
        max_chars: int,
    ) -> dict:
        if not path.exists():
            path.write_text(f"{default_header}\n\n", encoding="utf-8")
        raw = path.read_text(encoding="utf-8")
        before_chars = len(raw)
        lines = raw.splitlines()

        header_lines: list[str] = []
        entry_lines: list[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if not entry_lines and stripped.startswith("#"):
                header_lines.append(redact(stripped))
            else:
                entry_lines.append(redact(stripped))

        header = "\n".join(header_lines) if header_lines else default_header

        # Deduplikasi dari belakang agar catatan terbaru dengan isi identik dipertahankan.
        seen: set[str] = set()
        deduped_reversed: list[str] = []
        for entry in reversed(entry_lines):
            key = cls._entry_key(entry)
            if key in seen:
                continue
            seen.add(key)
            deduped_reversed.append(entry)
        kept = list(reversed(deduped_reversed))

        if max_entries >= 0 and len(kept) > max_entries:
            kept = kept[-max_entries:]

        prefix = f"{header}\n\n"
        budget = max(len(prefix), int(max_chars))
        while kept and len(prefix) + sum(len(item) + 1 for item in kept) > budget:
            kept.pop(0)

        new_text = prefix + ("\n".join(kept) + "\n" if kept else "")
        path.write_text(new_text, encoding="utf-8")
        return {
            "before_chars": before_chars,
            "after_chars": len(new_text),
            "before_entries": len(entry_lines),
            "after_entries": len(kept),
            "removed_entries": max(0, len(entry_lines) - len(kept)),
        }

    def prune(
        self,
        max_entries: int = 50,
        max_chars: int = 6000,
        target: str = "all",
    ) -> dict:
        target = (target or "all").strip().lower()
        if target not in {"all", "memory", "user"}:
            raise ValueError("target harus salah satu dari: all, memory, user")
        max_entries = max(0, int(max_entries))
        max_chars = max(256, int(max_chars))

        details: dict[str, dict] = {}
        if target in {"all", "memory"}:
            details["memory"] = self._prune_file(
                self.memory_file, MEMORY_HEADER, max_entries=max_entries, max_chars=max_chars
            )
        if target in {"all", "user"}:
            details["user"] = self._prune_file(
                self.user_file, USER_HEADER, max_entries=max_entries, max_chars=max_chars
            )

        return {
            "target": target,
            "max_entries": max_entries,
            "max_chars": max_chars,
            "before_chars": sum(d["before_chars"] for d in details.values()),
            "after_chars": sum(d["after_chars"] for d in details.values()),
            "removed_entries": sum(d["removed_entries"] for d in details.values()),
            "files": details,
        }
