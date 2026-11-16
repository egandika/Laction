"""
Server MCP demo (stdio, zero-dependency) untuk menguji klien MCP Laction.

Jalankan manual:
    python3 -m laction_agent.mcp.demo_server

Tools: `ping` dan `workspace_summary`. Hanya membaca — tidak menulis file.
Sengaja sederhana agar bisa dipakai sebagai contoh implementasi server.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "laction-demo", "version": "1.0.0"}

TOOLS = [
    {
        "name": "ping",
        "description": "Kembalikan 'pong' beserta pesan opsional; untuk menguji koneksi.",
        "inputSchema": {
            "type": "object",
            "properties": {"message": {"type": "string", "description": "Pesan opsional"}},
        },
    },
    {
        "name": "workspace_summary",
        "description": "Ringkas jumlah file & byte di workspace (maks 2 level, tanpa isi file).",
        "inputSchema": {
            "type": "object",
            "properties": {"max_entries": {"type": "integer", "minimum": 1, "maximum": 200}},
        },
    },
]


def _workspace() -> Path:
    return Path(os.environ.get("LACTION_WORKSPACE") or os.getcwd()).expanduser().resolve()


def _tool_ping(arguments: dict) -> str:
    message = str((arguments or {}).get("message", "")).strip()
    return f"pong{(': ' + message) if message else ''}"


def _tool_workspace_summary(arguments: dict) -> str:
    try:
        limit = min(max(int((arguments or {}).get("max_entries", 50)), 1), 200)
    except (TypeError, ValueError):
        limit = 50
    root = _workspace()
    if not root.exists():
        return f"ERROR: workspace tidak ditemukan: {root}"
    files = 0
    total_bytes = 0
    for current, dirs, filenames in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in {"__pycache__", "node_modules", ".venv"}]
        for name in filenames:
            path = Path(current) / name
            try:
                total_bytes += path.stat().st_size
            except OSError:
                continue
            files += 1
            if files >= limit * 20:
                break
        if files >= limit * 20:
            break
    return json.dumps(
        {"workspace": str(root), "files_counted": files, "bytes_counted": total_bytes},
        ensure_ascii=False,
    )


_HANDLERS = {"ping": _tool_ping, "workspace_summary": _tool_workspace_summary}


def handle(message: dict) -> dict | None:
    method = message.get("method")
    request_id = message.get("id")
    is_notification = "id" not in message

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": SERVER_INFO,
            },
        }
    if method and method.startswith("notifications/"):
        return None
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = message.get("params") or {}
        name = str(params.get("name", ""))
        handler = _HANDLERS.get(name)
        if handler is None:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32602, "message": f"tool tidak dikenal: {name}"},
            }
        try:
            text = handler(params.get("arguments") or {})
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"content": [{"type": "text", "text": text}], "isError": False},
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"content": [{"type": "text", "text": f"ERROR: {exc}"}], "isError": True},
            }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if is_notification:
        return None
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": f"method tidak didukung: {method}"},
    }


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}) + "\n")
            sys.stdout.flush()
            continue
        if not isinstance(message, dict):
            continue
        response = handle(message)
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
