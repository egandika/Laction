"""
Registry server MCP yang diizinkan (allowlist eksplisit).

Disimpan di `<LACTION_HOME>/mcp_servers.json`:

```json
{
  "servers": [
    {"name": "demo", "command": "python3", "args": ["-m", "laction_agent.mcp.demo_server"], "enabled": true}
  ]
}
```

Desain keamanan: hanya server yang terdaftar manual yang bisa dijalankan —
tidak ada auto-discovery dari file proyek, dan `write_file` agent diblokir
dari menulis file ini (lihat `file_tools.PROTECTED_FILENAMES`).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

SERVER_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
MAX_ARGS = 32
MAX_ARG_CHARS = 512


class MCPRegistry:
    def __init__(self, home: Path, filename: str = "mcp_servers.json"):
        self.home = Path(home)
        self.home.mkdir(parents=True, exist_ok=True)
        self.path = self.home / filename

    # ---------- IO ----------
    def _read(self) -> dict:
        if not self.path.exists():
            return {"servers": []}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8") or "{}")
        except (OSError, json.JSONDecodeError):
            return {"servers": []}
        if not isinstance(data, dict):
            return {"servers": []}
        servers = data.get("servers")
        return {"servers": servers if isinstance(servers, list) else []}

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        try:
            self.path.chmod(0o600)
        except OSError:
            pass

    # ---------- validasi ----------
    @staticmethod
    def validate_server(raw: dict) -> dict:
        if not isinstance(raw, dict):
            raise ValueError("definisi server harus objek JSON")
        name = str(raw.get("name", "")).strip().lower()
        if not SERVER_NAME_RE.match(name):
            raise ValueError("nama server: huruf kecil/angka/strip, 1–32 karakter")
        command = str(raw.get("command", "")).strip()
        if not command or " " in command or len(command) > 256:
            raise ValueError("command wajib berupa path/binary tunggal tanpa spasi")
        args = raw.get("args") or []
        if not isinstance(args, list) or len(args) > MAX_ARGS:
            raise ValueError(f"args harus list (maks {MAX_ARGS} item)")
        clean_args: list[str] = []
        for arg in args:
            text = str(arg)
            if len(text) > MAX_ARG_CHARS:
                raise ValueError(f"argumen melebihi {MAX_ARG_CHARS} karakter")
            clean_args.append(text)
        env = raw.get("env") or {}
        if not isinstance(env, dict):
            raise ValueError("env harus objek string->string")
        clean_env: dict[str, str] = {}
        for key, value in env.items():
            key_str = str(key).strip()
            if not re.match(r"^[A-Z_][A-Z0-9_]{0,63}$", key_str):
                raise ValueError(f"nama env variable tidak valid: {key_str}")
            clean_env[key_str] = str(value)[:MAX_ARG_CHARS]
        return {
            "name": name,
            "command": command,
            "args": clean_args,
            "env": clean_env,
            "enabled": bool(raw.get("enabled", True)),
            "description": str(raw.get("description", ""))[:200],
        }

    # ---------- API ----------
    def list_servers(self) -> list[dict]:
        out: list[dict] = []
        for raw in self._read()["servers"]:
            try:
                out.append(self.validate_server(raw))
            except ValueError:
                continue
        return out

    def get(self, name: str) -> dict | None:
        wanted = str(name or "").strip().lower()
        for server in self.list_servers():
            if server["name"] == wanted:
                return server
        return None

    def add_server(self, name: str, command: str, args: list[str] | None = None, env: dict | None = None, description: str = "") -> dict:
        server = self.validate_server(
            {
                "name": name,
                "command": command,
                "args": args or [],
                "env": env or {},
                "enabled": True,
                "description": description,
            }
        )
        data = self._read()
        kept = [
            raw for raw in data["servers"]
            if not (isinstance(raw, dict) and str(raw.get("name", "")).strip().lower() == server["name"])
        ]
        kept.append(server)
        self._write({"servers": kept})
        return server

    def remove_server(self, name: str) -> bool:
        wanted = str(name or "").strip().lower()
        data = self._read()
        kept = [
            raw for raw in data["servers"]
            if not (isinstance(raw, dict) and str(raw.get("name", "")).strip().lower() == wanted)
        ]
        if len(kept) == len(data["servers"]):
            return False
        self._write({"servers": kept})
        return True

    def set_enabled(self, name: str, enabled: bool) -> bool:
        wanted = str(name or "").strip().lower()
        data = self._read()
        changed = False
        for raw in data["servers"]:
            if isinstance(raw, dict) and str(raw.get("name", "")).strip().lower() == wanted:
                raw["enabled"] = bool(enabled)
                changed = True
        if changed:
            self._write(data)
        return changed
