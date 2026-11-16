"""Tools MCP: daftar server yang diizinkan, daftar tool server, dan panggil tool MCP."""
from __future__ import annotations

import json
from pathlib import Path

from ..mcp.client import MCPError, MCPStdioClient
from ..mcp.registry import MCPRegistry
from ..utils import redact, truncate
from .registry import get_registry

reg = get_registry()
MCP_CALL_TIMEOUT = 30


def _home(context: dict | None = None) -> Path:
    cfg = (context or {}).get("cfg")
    home = getattr(cfg, "home", None) or (context or {}).get("home") or "./data"
    return Path(home).expanduser()


def _registry(context: dict | None = None) -> MCPRegistry:
    return MCPRegistry(_home(context))


def _server(context: dict | None, name: str) -> dict | None:
    return _registry(context).get(str(name or "").strip())


@reg.register(
    "mcp_list_servers",
    "Daftar server MCP yang terdaftar di allowlist (tidak menjalankan apa pun).",
    {"type": "object", "properties": {}},
)
def mcp_list_servers(context: dict | None = None) -> str:
    servers = _registry(context).list_servers()
    if not servers:
        return "Belum ada server MCP terdaftar. Tambahkan via `laction mcp add --name demo --command python3 --args ...`."
    return "\n".join(
        f"- {s['name']} ({'enabled' if s['enabled'] else 'disabled'}): {s['command']} {' '.join(s['args'])}"
        for s in servers
    )


@reg.register(
    "mcp_list_tools",
    "Hubungkan ke satu server MCP terdaftar lalu tampilkan daftar tool-nya.",
    {"type": "object", "properties": {"server": {"type": "string"}}, "required": ["server"]},
)
def mcp_list_tools(server: str, context: dict | None = None) -> str:
    definition = _server(context, server)
    if definition is None:
        return f"DITOLAK: server MCP '{server}' tidak ada di allowlist."
    if not definition["enabled"]:
        return f"DITOLAK: server MCP '{server}' dinonaktifkan."
    try:
        with MCPStdioClient(
            definition["command"], definition["args"], definition["env"], timeout=20
        ) as client:
            info = client.initialize()
            tools = client.list_tools()
    except MCPError as exc:
        return f"ERROR MCP: {redact(str(exc))}"
    header = f"Server {server} ({info.get('serverInfo', {}).get('name', '?')}, protocol {info.get('protocolVersion')}):"
    if not tools:
        return header + "\n(tidak ada tool)"
    return header + "\n" + "\n".join(f"- {t['name']}: {t['description']}" for t in tools)


@reg.register(
    "mcp_call",
    "Panggil satu tool pada server MCP terdaftar (server dijalankan sementara di container proses lokal). Perlu approval karena eksekusi kode pihak ketiga.",
    {
        "type": "object",
        "properties": {
            "server": {"type": "string", "description": "Nama server MCP terdaftar"},
            "tool": {"type": "string", "description": "Nama tool pada server tersebut"},
            "arguments": {"type": "object", "description": "Argumen sesuai inputSchema tool"},
        },
        "required": ["server", "tool"],
    },
    dangerous=True,
)
def mcp_call(
    server: str,
    tool: str,
    arguments: dict | None = None,
    context: dict | None = None,
) -> str:
    context = context or {}
    cfg = context.get("cfg")
    mode = str(context.get("approval_mode", getattr(cfg, "approval_mode", "smart"))).lower()
    if mode == "never":
        return "DITOLAK: MCP call diblokir pada approval_mode=never."
    if arguments is not None and not isinstance(arguments, dict):
        return "ERROR: arguments harus objek JSON."

    definition = _server(context, server)
    if definition is None:
        return f"DITOLAK: server MCP '{server}' tidak ada di allowlist."
    if not definition["enabled"]:
        return f"DITOLAK: server MCP '{server}' dinonaktifkan."

    approve = context.get("approve")
    if approve is None:
        return (
            "PERLU APPROVAL: mcp_call menjalankan proses pihak ketiga dan tidak berjalan otomatis. "
            "Gunakan CLI interaktif atau gateway dengan approval."
        )
    try:
        if not approve(f"mcp_call {server}.{tool}:\n{truncate(redact(json.dumps(arguments or {}, ensure_ascii=False)), 400)}"):
            return "DITOLAK: user tidak menyetujui pemanggilan tool MCP."
    except Exception as exc:  # noqa: BLE001
        return f"DITOLAK: gagal meminta approval: {exc}"

    try:
        with MCPStdioClient(
            definition["command"], definition["args"], definition["env"], timeout=MCP_CALL_TIMEOUT
        ) as client:
            client.initialize()
            available = {t["name"]: t for t in client.list_tools()}
            if tool not in available:
                return (
                    f"DITOLAK: tool '{tool}' tidak ada di server '{server}'. "
                    f"Tersedia: {', '.join(sorted(available)) or '-'}"
                )
            schema = available[tool].get("inputSchema") or {}
            if schema.get("type", "object") != "object":
                return "DITOLAK: skema tool tidak mendukung argumen objek."
            required = schema.get("required") or []
            missing = [key for key in required if not isinstance(arguments, dict) or key not in arguments]
            if missing:
                return f"ERROR: argumen wajib belum diisi: {', '.join(missing)}"
            result = client.call_tool(tool, arguments or {})
    except MCPError as exc:
        return f"ERROR MCP: {redact(str(exc))}"
    return truncate(redact(result), 6000)
