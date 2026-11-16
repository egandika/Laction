"""
Minimal MCP client: JSON-RPC 2.0 over stdio, stdlib-only.

Alur protokol: `initialize` -> `notifications/initialized` -> `tools/list` /
`tools/call`. Batasan yang disengaja:
- Frame maksimum 1 MiB (mencegah memory blow-up dari server jahat).
- Timeout wall-clock per request, proses dibunuh bila melewati batas.
- Environment host TIDAK diwarisi: hanya `PATH`/`HOME`/LANG + env server
  eksplisit, jadi `LACTION_API_KEY` dsb tidak bocor ke proses anak.
"""
from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import threading
import time

MAX_FRAME_BYTES = 1024 * 1024
DEFAULT_TIMEOUT = 20
PROTOCOL_VERSION = "2024-11-05"
_ENV_ALLOWLIST = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT")


class MCPError(RuntimeError):
    pass


def _base_env(extra: dict | None = None) -> dict[str, str]:
    env = {k: os.environ[k] for k in _ENV_ALLOWLIST if k in os.environ}
    for key, value in (extra or {}).items():
        env[str(key)] = str(value)
    return env


class MCPStdioClient:
    """Satu koneksi ke satu server MCP (spawn per pemakaian)."""

    def __init__(self, command: str, args: list[str] | None = None, env: dict | None = None, timeout: float = DEFAULT_TIMEOUT):
        self.command = command
        self.args = list(args or [])
        self.env = _base_env(env)
        self.timeout = max(1.0, float(timeout))
        self._proc: subprocess.Popen | None = None
        self._next_id = 0
        self._lines: queue.Queue = queue.Queue()
        self._reader: threading.Thread | None = None
        self.server_info: dict = {}

    # ---------- lifecycle ----------
    def __enter__(self) -> "MCPStdioClient":
        self.start()
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def start(self) -> None:
        resolved = shutil.which(self.command) or self.command
        try:
            self._proc = subprocess.Popen(
                [resolved, *self.args],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=self.env,
                cwd=os.environ.get("LACTION_WORKSPACE") or None,
            )
        except OSError as exc:
            raise MCPError(f"gagal menjalankan server MCP '{self.command}': {exc}") from exc
        self._reader = threading.Thread(target=self._pump, name="mcp-reader", daemon=True)
        self._reader.start()

    def _pump(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        for line in proc.stdout:
            if len(line) > MAX_FRAME_BYTES:
                self._lines.put(MCPError(f"frame melebihi {MAX_FRAME_BYTES} byte"))
                break
            self._lines.put(line)
        self._lines.put(None)

    def close(self) -> None:
        proc = self._proc
        self._proc = None
        if proc is None:
            return
        try:
            if proc.stdin:
                proc.stdin.close()
        except OSError:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            try:
                proc.kill()
                proc.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                pass
        if proc.stdout:
            try:
                proc.stdout.close()
            except OSError:
                pass

    # ---------- transport ----------
    def _send(self, payload: dict) -> None:
        if self._proc is None or self._proc.stdin is None:
            raise MCPError("server MCP belum berjalan")
        frame = json.dumps(payload, ensure_ascii=False) + "\n"
        if len(frame.encode("utf-8")) > MAX_FRAME_BYTES:
            raise MCPError("request melebihi batas frame")
        try:
            self._proc.stdin.write(frame)
            self._proc.stdin.flush()
        except OSError as exc:
            raise MCPError(f"gagal menulis ke server MCP: {exc}") from exc

    def _read_message(self, deadline: float) -> dict:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise MCPError(f"timeout menunggu respons server MCP ({self.timeout:.0f}s)")
            try:
                line = self._lines.get(timeout=remaining)
            except queue.Empty as exc:
                raise MCPError(f"timeout menunggu respons server MCP ({self.timeout:.0f}s)") from exc
            if line is None:
                raise MCPError("server MCP menutup stdout sebelum membalas")
            if isinstance(line, MCPError):
                raise line
            text = line.strip()
            if not text:
                continue
            try:
                message = json.loads(text)
            except json.JSONDecodeError as exc:
                raise MCPError(f"frame JSON tidak valid dari server MCP: {text[:120]}") from exc
            if isinstance(message, dict):
                return message
            raise MCPError("frame MCP bukan objek JSON")

    def request(self, method: str, params: dict | None = None) -> dict:
        self._next_id += 1
        request_id = self._next_id
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}})
        deadline = time.monotonic() + self.timeout
        while True:
            message = self._read_message(deadline)
            # Lewati notifikasi/log server yang tidak punya id.
            if message.get("id") != request_id:
                if "method" in message and "id" not in message:
                    continue
                continue
            if "error" in message and message["error"]:
                err = message["error"]
                detail = err.get("message") if isinstance(err, dict) else str(err)
                raise MCPError(f"{method} gagal: {detail}")
            result = message.get("result")
            return result if isinstance(result, dict) else {"result": result}

    def notify(self, method: str, params: dict | None = None) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    # ---------- MCP API ----------
    def initialize(self) -> dict:
        result = self.request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "laction", "version": "1.0"},
            },
        )
        self.server_info = {
            "protocolVersion": result.get("protocolVersion", PROTOCOL_VERSION),
            "serverInfo": result.get("serverInfo", {}),
            "capabilities": sorted((result.get("capabilities") or {}).keys()),
        }
        self.notify("notifications/initialized")
        return self.server_info

    def list_tools(self) -> list[dict]:
        result = self.request("tools/list", {})
        tools = result.get("tools") or []
        clean: list[dict] = []
        for tool in tools if isinstance(tools, list) else []:
            if not isinstance(tool, dict):
                continue
            name = str(tool.get("name", "")).strip()
            if not name:
                continue
            schema = tool.get("inputSchema")
            clean.append(
                {
                    "name": name,
                    "description": str(tool.get("description", ""))[:400],
                    "inputSchema": schema if isinstance(schema, dict) else {"type": "object", "properties": {}},
                }
            )
        return clean

    def call_tool(self, name: str, arguments: dict | None = None, timeout: float | None = None) -> str:
        previous = self.timeout
        if timeout is not None:
            self.timeout = max(1.0, float(timeout))
        try:
            result = self.request("tools/call", {"name": name, "arguments": arguments or {}})
        finally:
            self.timeout = previous
        chunks: list[str] = []
        for item in result.get("content") or []:
            if isinstance(item, dict) and item.get("type") == "text":
                chunks.append(str(item.get("text", "")))
        text = "\n".join(chunk for chunk in chunks if chunk)
        if not text:
            text = json.dumps(result, ensure_ascii=False)
        if result.get("isError"):
            return f"ERROR MCP: {text}"
        return text
