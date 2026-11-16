"""
Memory Manager — Tier 1 Hermes-style: MEMORY.md + USER.md.

Kedua file dimuat ke system prompt setiap sesi (nol latensi retrieval).
Agent "nudges" dirinya sendiri untuk menyimpan hal penting.
"""
from __future__ import annotations

import datetime
from pathlib import Path


class MemoryManager:
    def __init__(self, home: Path):
        self.home = Path(home)
        self.home.mkdir(parents=True, exist_ok=True)
        self.memory_file = self.home / "MEMORY.md"
        self.user_file = self.home / "USER.md"
        self._ensure()

    def _ensure(self):
        if not self.memory_file.exists():
            self.memory_file.write_text("# MEMORY.md — Ingatan jangka panjang Laction Agent\n\n", encoding="utf-8")
        if not self.user_file.exists():
            self.user_file.write_text("# USER.md — Profil & preferensi user\n\n", encoding="utf-8")

    def read_memory(self) -> str:
        return self.memory_file.read_text(encoding="utf-8").strip()

    def read_user(self) -> str:
        return self.user_file.read_text(encoding="utf-8").strip()

    def read_all(self) -> str:
        return f"--- MEMORY.md ---\n{self.read_memory()}\n\n--- USER.md ---\n{self.read_user()}"

    def append_memory(self, note: str):
        stamp = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
        with self.memory_file.open("a", encoding="utf-8") as f:
            f.write(f"- [{stamp}] {note}\n")

    def append_user(self, note: str):
        stamp = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
        with self.user_file.open("a", encoding="utf-8") as f:
            f.write(f"- [{stamp}] {note}\n")
