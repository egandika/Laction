"""
Session DB — Tier 2: SQLite lokal untuk riwayat sesi & observability tool.

Mendukung pencarian full-text **SQLite FTS5** (ranking BM25 + prefix kata)
dengan fallback otomatis ke `LIKE` bila FTS5 tidak tersedia di build SQLite
atau ketika kueri berupa simbol/substring non-token. Juga menyimpan jejak
eksekusi tool terstruktur (`tool_events`) untuk observability lokal.
"""
from __future__ import annotations

import datetime
import re
import sqlite3
import uuid
from pathlib import Path

from ..utils import redact, truncate

_FTS_TOKEN_RE = re.compile(r"\w+", re.UNICODE)
# Batas waktu tunggu lock SQLite: dua proses (cron + gateway) bisa menulis
# bersamaan, dan default 5 detik terlalu cepat untuk DB yang sedang di-backfill.
SQLITE_TIMEOUT_SECONDS = 10.0


class SessionDB:
    def __init__(self, home: Path, enable_fts: bool = True):
        self.db_path = Path(home) / "sessions.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._prefer_fts = enable_fts
        self.fts_enabled = False
        self.recovered_from = ""
        self.last_error = ""
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=SQLITE_TIMEOUT_SECONDS)
        conn.row_factory = sqlite3.Row
        # WAL: pembaca (traces/history) tidak memblokir penulis (agent run) dan
        # tahan terhadap dua proses memakai HOME yang sama.
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
        except sqlite3.DatabaseError:
            # DB korup/terkunci: biarkan lapisan _init yang memutuskan pemulihan.
            pass
        return conn

    def _init(self):
        try:
            conn = self._connect()
            try:
                self._init_schema(conn)
            finally:
                conn.close()
            return
        except sqlite3.DatabaseError as exc:
            # DB korup: karantina sekali, lalu buat ulang agar agent tidak mati total.
            if not self._recover_corrupt_db(exc):
                raise
        conn = self._connect()
        try:
            self._init_schema(conn)
        finally:
            conn.close()

    def _recover_corrupt_db(self, exc: Exception) -> bool:
        stamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        quarantined = self.db_path.with_name(f"{self.db_path.name}.corrupt-{stamp}")
        try:
            self.db_path.rename(quarantined)
            # Sidecar WAL/SHM ikut dipindah agar tidak menempel ke DB baru.
            for suffix in ("-wal", "-shm"):
                sidecar = self.db_path.with_name(self.db_path.name + suffix)
                if sidecar.exists():
                    sidecar.rename(sidecar.with_name(sidecar.name + f".corrupt-{stamp}"))
        except OSError:
            return False
        self.fts_enabled = False
        self.recovered_from = str(quarantined)
        self.last_error = str(exc)
        return True

    def _init_schema(self, conn: sqlite3.Connection) -> None:
        with conn:
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
            conn.execute(
                """CREATE TABLE IF NOT EXISTS tool_events (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    duration_ms INTEGER NOT NULL,
                    args_preview TEXT NOT NULL,
                    result_preview TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )"""
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tool_events_session ON tool_events(session_id)"
            )
            if self._prefer_fts:
                try:
                    conn.execute(
                        """CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
                            message_id UNINDEXED,
                            session_id UNINDEXED,
                            role UNINDEXED,
                            content,
                            created_at UNINDEXED,
                            tokenize='unicode61'
                        )"""
                    )
                    conn.execute(
                        """INSERT INTO messages_fts (message_id, session_id, role, content, created_at)
                        SELECT m.id, m.session_id, m.role, m.content, m.created_at
                        FROM messages m
                        WHERE NOT EXISTS (
                            SELECT 1 FROM messages_fts f WHERE f.message_id = m.id
                        )"""
                    )
                    self.fts_enabled = True
                except sqlite3.OperationalError:
                    self.fts_enabled = False

    def new_session(self) -> str:
        return f"s-{uuid.uuid4().hex[:8]}"

    def save(self, session_id: str, role: str, content: str):
        msg_id = uuid.uuid4().hex
        now = datetime.datetime.now().astimezone().isoformat()
        clean = redact(content)
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO messages (id, session_id, role, content, created_at) VALUES (?,?,?,?,?)",
                (msg_id, session_id, role, clean, now),
            )
            if self.fts_enabled:
                try:
                    conn.execute(
                        "INSERT INTO messages_fts (message_id, session_id, role, content, created_at) VALUES (?,?,?,?,?)",
                        (msg_id, session_id, role, clean, now),
                    )
                except sqlite3.OperationalError:
                    self.fts_enabled = False

    def history(self, session_id: str, limit: int = 50) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT role, content FROM messages WHERE session_id=? ORDER BY created_at DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    @staticmethod
    def _fts_query(query: str) -> str:
        tokens = [tok for tok in _FTS_TOKEN_RE.findall(query or "") if tok]
        if not tokens:
            return ""
        return " ".join(f'"{tok}"*' for tok in tokens[:12])

    def search(self, query: str, limit: int = 10) -> list[dict]:
        limit = max(1, int(limit))
        raw = (query or "").strip()
        with self._connect() as conn:
            if not raw:
                rows = conn.execute(
                    "SELECT session_id, role, content, created_at FROM messages ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                return [dict(r) for r in rows]

            if self.fts_enabled:
                fts_expr = self._fts_query(raw)
                if fts_expr:
                    try:
                        rows = conn.execute(
                            """SELECT session_id, role, content, created_at,
                                      bm25(messages_fts) AS rank
                               FROM messages_fts
                               WHERE messages_fts MATCH ?
                               ORDER BY rank ASC, created_at DESC
                               LIMIT ?""",
                            (fts_expr, limit),
                        ).fetchall()
                        if rows:
                            return [
                                {
                                    "session_id": r["session_id"],
                                    "role": r["role"],
                                    "content": r["content"],
                                    "created_at": r["created_at"],
                                }
                                for r in rows
                            ]
                    except sqlite3.OperationalError:
                        pass

            rows = conn.execute(
                "SELECT session_id, role, content, created_at FROM messages WHERE content LIKE ? ORDER BY created_at DESC LIMIT ?",
                (f"%{raw}%", limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def record_tool_event(
        self,
        session_id: str,
        tool_name: str,
        status: str,
        duration_ms: int,
        args_preview: str = "",
        result_preview: str = "",
    ) -> None:
        now = datetime.datetime.now().astimezone().isoformat()
        clean_args = truncate(redact(str(args_preview or "")), 240)
        clean_result = truncate(redact(str(result_preview or "")), 240)
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO tool_events
                (id, session_id, tool_name, status, duration_ms, args_preview, result_preview, created_at)
                VALUES (?,?,?,?,?,?,?,?)""",
                (
                    uuid.uuid4().hex,
                    session_id,
                    str(tool_name),
                    str(status),
                    max(0, int(duration_ms)),
                    clean_args,
                    clean_result,
                    now,
                ),
            )

    def tool_events(self, session_id: str | None = None, limit: int = 50) -> list[dict]:
        limit = min(max(1, int(limit)), 500)
        with self._connect() as conn:
            if session_id:
                rows = conn.execute(
                    """SELECT session_id, tool_name, status, duration_ms, args_preview, result_preview, created_at
                       FROM tool_events WHERE session_id=? ORDER BY created_at DESC LIMIT ?""",
                    (session_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT session_id, tool_name, status, duration_ms, args_preview, result_preview, created_at
                       FROM tool_events ORDER BY created_at DESC LIMIT ?""",
                    (limit,),
                ).fetchall()
        return [dict(r) for r in rows]

    def stats(self) -> dict:
        """Ringkasan isi DB untuk `status`/`doctor` (bukan data sensitif)."""
        with self._connect() as conn:
            messages = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            sessions = conn.execute("SELECT COUNT(DISTINCT session_id) FROM messages").fetchone()[0]
            events = conn.execute("SELECT COUNT(*) FROM tool_events").fetchone()[0]
        try:
            size_bytes = self.db_path.stat().st_size
        except OSError:
            size_bytes = 0
        return {
            "messages": int(messages),
            "sessions": int(sessions),
            "tool_events": int(events),
            "size_bytes": size_bytes,
            "fts_enabled": self.fts_enabled,
            "recovered_from": self.recovered_from,
        }

    def prune_tool_events(self, keep: int = 10_000) -> dict:
        """Simpan hanya `keep` event terbaru; sisanya dihapus.

        `tool_events` tumbuh setiap panggilan tool. Tanpa retensi, DB gateway
        yang berjalan lama bisa membengkak dan `laction traces` makin lambat.
        Baris pesan/riwayat chat tidak disentuh.
        """
        keep = max(0, int(keep))
        with self._connect() as conn:
            before = conn.execute("SELECT COUNT(*) FROM tool_events").fetchone()[0]
            if before <= keep:
                return {"before": int(before), "after": int(before), "deleted": 0, "keep": keep}
            conn.execute(
                """DELETE FROM tool_events WHERE id NOT IN (
                    SELECT id FROM tool_events ORDER BY created_at DESC LIMIT ?
                )""",
                (keep,),
            )
            after = conn.execute("SELECT COUNT(*) FROM tool_events").fetchone()[0]
        return {
            "before": int(before),
            "after": int(after),
            "deleted": int(before) - int(after),
            "keep": keep,
        }

    def tool_metrics(self, session_id: str | None = None) -> dict:
        where = "WHERE session_id=?" if session_id else ""
        params = (session_id,) if session_id else ()
        with self._connect() as conn:
            summary = conn.execute(
                f"""SELECT COUNT(*) AS total,
                           COALESCE(AVG(duration_ms), 0) AS avg_ms,
                           COALESCE(MAX(duration_ms), 0) AS max_ms
                    FROM tool_events {where}""",
                params,
            ).fetchone()
            status_rows = conn.execute(
                f"SELECT status, COUNT(*) AS cnt FROM tool_events {where} GROUP BY status",
                params,
            ).fetchall()
            tool_rows = conn.execute(
                f"""SELECT tool_name,
                           COUNT(*) AS calls,
                           SUM(CASE WHEN status != 'ok' THEN 1 ELSE 0 END) AS non_ok,
                           ROUND(AVG(duration_ms), 1) AS avg_ms
                    FROM tool_events {where}
                    GROUP BY tool_name
                    ORDER BY calls DESC, tool_name ASC""",
                params,
            ).fetchall()
        by_status = {r["status"]: int(r["cnt"]) for r in status_rows}
        return {
            "total_calls": int(summary["total"] or 0),
            "avg_duration_ms": round(float(summary["avg_ms"] or 0.0), 1),
            "max_duration_ms": int(summary["max_ms"] or 0),
            "by_status": by_status,
            "by_tool": [
                {
                    "tool": r["tool_name"],
                    "calls": int(r["calls"]),
                    "non_ok": int(r["non_ok"] or 0),
                    "avg_ms": float(r["avg_ms"] or 0.0),
                }
                for r in tool_rows
            ],
        }
