"""Tools MCP: daftar server yang diizinkan, daftar tool server, dan panggil tool MCP."""
from __future__ import annotations

import json
import os
from pathlib import Path

from ..mcp.client import MCPError, MCPStdioClient
from ..mcp.registry import MCPRegistry
from ..utils import redact, truncate
from .registry import get_registry

reg = get_registry()
MCP_CALL_TIMEOUT = 30


def _home(context: dict | None = None) -> Path:
    ctx = context or {}
    cfg = ctx.get("cfg")
    home = (
        getattr(cfg, "home", None)
        or ctx.get("home")
        or os.environ.get("LACTION_HOME")
        or "./data"
    )
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


def _preview_arguments(arguments: dict | None) -> str:
    return truncate(redact(json.dumps(arguments or {}, ensure_ascii=False)), 400)


def _allowed_tools_summary(definition: dict) -> str:
    allowed = definition.get("tools") or []
    return ", ".join(allowed) if allowed else "semua tool server"


def _clean_arguments(arguments: dict | None, schema: dict) -> tuple[dict, str]:
    """Validasi ringan argumen terhadap inputSchema: wajib-isi + tipe primitif.

    Bukan JSON Schema lengkap (zero dependency), tetapi menolak kasus yang paling
    berbahaya: argumen wajib hilang, tipe salah, atau argumen tak dikenal yang
    bisa mengejutkan server.
    """
    args = dict(arguments or {})
    properties = schema.get("properties") or {}
    if not isinstance(properties, dict):
        properties = {}
    required = schema.get("required") or []
    missing = [key for key in required if key not in args]
    if missing:
        return {}, f"ERROR: argumen wajib belum diisi: {', '.join(sorted(map(str, missing)))}"
    if properties and schema.get("additionalProperties") is False:
        unexpected = [key for key in args if key not in properties]
        if unexpected:
            return {}, f"ERROR: argumen tidak dikenal: {', '.join(sorted(map(str, unexpected)))}"

    type_map = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "array": list,
        "object": dict,
    }
    for key, value in args.items():
        spec = properties.get(key)
        if not isinstance(spec, dict):
            continue
        expected = spec.get("type")
        if not isinstance(expected, str) or expected not in type_map:
            continue
        if expected == "boolean" and isinstance(value, bool):
            continue
        if expected in {"integer", "number"} and isinstance(value, bool):
            return {}, f"ERROR: argumen '{key}' harus {expected}, bukan boolean."
        if not isinstance(value, type_map[expected]):
            return {}, f"ERROR: argumen '{key}' harus bertipe {expected}."
        if isinstance(value, str) and len(value) > 8000:
            return {}, f"ERROR: argumen '{key}' melebihi 8000 karakter."
    try:
        if len(json.dumps(args, ensure_ascii=False)) > 64 * 1024:
            return {}, "ERROR: total argumen melebihi 64 KiB."
    except (TypeError, ValueError) as exc:
        return {}, f"ERROR: argumen tidak dapat diserialisasi: {exc}"
    return args, ""


@reg.register(
    "mcp_call",
    "Panggil satu tool pada server MCP terdaftar (stdio, proses pihak ketiga). Wajib approval, dibatasi allowlist per-server/per-tool, dan argumen divalidasi terhadap inputSchema.",
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

    tool_name = str(tool or "").strip()
    if not tool_name:
        return "ERROR: nama tool wajib diisi."
    definition = _server(context, server)
    if definition is None:
        return f"DITOLAK: server MCP '{server}' tidak ada di allowlist."
    if not definition["enabled"]:
        return f"DITOLAK: server MCP '{server}' dinonaktifkan."
    allowed = definition.get("tools") or []
    if allowed and tool_name not in allowed:
        return (
            f"DITOLAK: tool '{tool_name}' tidak ada di allowlist server '{server}'. "
            f"Diizinkan: {', '.join(allowed)}"
        )

    # Approval diminta SEBELUM server dijalankan: proses pihak ketiga baru
    # di-spawn setelah user melihat server + tool + argumen yang di-redaksi.
    approve = context.get("approve")
    if approve is None:
        return (
            "PERLU APPROVAL: mcp_call menjalankan proses pihak ketiga dan tidak berjalan otomatis. "
            "Gunakan CLI interaktif atau gateway dengan approval."
        )
    try:
        if not approve(
            f"mcp_call {definition['name']}.{tool_name} "
            f"(allowlist: {_allowed_tools_summary(definition)}):\n{_preview_arguments(arguments)}"
        ):
            return "DITOLAK: user tidak menyetujui pemanggilan tool MCP."
    except Exception as exc:  # noqa: BLE001
        return f"DITOLAK: gagal meminta approval: {exc}"

    try:
        with MCPStdioClient(
            definition["command"], definition["args"], definition["env"], timeout=MCP_CALL_TIMEOUT
        ) as client:
            client.initialize()
            available = {t["name"]: t for t in client.list_tools()}
            if tool_name not in available:
                return (
                    f"DITOLAK: tool '{tool_name}' tidak ada di server '{server}'. "
                    f"Tersedia: {', '.join(sorted(available)) or '-'}"
                )
            schema = available[tool_name].get("inputSchema") or {}
            if schema.get("type", "object") != "object":
                return "DITOLAK: skema tool tidak mendukung argumen objek."
            clean, error = _clean_arguments(arguments, schema)
            if error:
                return error
            result = client.call_tool(tool_name, clean)
    except MCPError as exc:
        return f"ERROR MCP: {redact(str(exc))}"
    return truncate(redact(result), 6000)
