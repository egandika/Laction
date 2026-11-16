"""
Session DB — Tier 2: SQLite lokal untuk riwayat sesi.

Menyimpan setiap pesan & tool call, plus pencarian sederhana
(mirip FTS5 Hermes, tapi pakai LIKE agar zero-dependency).
"""
from __future__ import annotations

import datetime
import sqlite3
import uuid
from pathlib import Path


class SessionDB:
    def __init__(self, home: Path):
        self.db_path = Path(home) / "sessions.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self):
        with self._connect() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )"""
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_session ON messages(session_id)")

    def new_session(self) -> str:
        return f"s-{uuid.uuid4().hex[:8]}"

    def save(self, session_id: str, role: str, content: str):
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO messages (id, session_id, role, content, created_at) VALUES (?,?,?,?,?)",
                (uuid.uuid4().hex, session_id, role, content, datetime.datetime.now().astimezone().isoformat()),
            )

    def history(self, session_id: str, limit: int = 50) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT role, content FROM messages WHERE session_id=? ORDER BY created_at DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    def search(self, query: str, limit: int = 10) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT session_id, role, content, created_at FROM messages WHERE content LIKE ? ORDER BY created_at DESC LIMIT ?",
                (f"%{query}%", limit),
            ).fetchall()
        return [dict(r) for r in rows]
