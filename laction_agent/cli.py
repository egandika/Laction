"""
CLI Laction Agent.

Cara pakai:
    laction "list file"                 # one-shot
    laction chat                        # REPL interaktif
    laction status                      # inspeksi konfigurasi
    laction gateway --port 8000         # UI + HTTP API
    python3 -m laction_agent "halo"     # tanpa install
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
import time
from pathlib import Path

try:  # history input di terminal, opsional
    import readline  # noqa: F401
except ImportError:
    pass

from . import __version__
from .agent import AIAgent
from .policies import READ_ONLY_TOOLS
from .config import Config, VALID_APPROVAL_MODES, VALID_PROVIDERS, VALID_SANDBOX_MODES
from .cron.scheduler import CronScheduler
from .mcp.client import MCPError, MCPStdioClient
from .mcp.registry import MCPRegistry
from .memory.manager import MemoryManager
from .memory.session_db import SessionDB
from .sandbox import DockerExecutor, resolve_execution_backend
from .skills.manager import SkillManager
from .tools.registry import get_registry
from .tools.terminal_tool import _is_dangerous
from .tools.web_tools import _is_blocked_url
from .utils import log, redact

try:
    from .gateway import run_server
except ImportError:  # pragma: no cover — hanya bila gateway belum ada
    run_server = None  # type: ignore[assignment]

KNOWN_COMMANDS = {
    "chat", "run", "init", "status", "tools", "skills", "memory", "cron", "gateway",
    "doctor", "traces", "mcp",
}


def _add_global_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--version", action="version", version=f"laction-agent {__version__}")
    p.add_argument("--config", help="Path config.yaml (default: ./config.yaml)")
    p.add_argument("--home", help="Override LACTION_HOME (direktori profil/data)")
    p.add_argument("--provider", choices=sorted(VALID_PROVIDERS), help="Override provider LLM")
    p.add_argument("--model", help="Override nama model")
    p.add_argument("--api-base", dest="api_base", help="Override base URL OpenAI-compatible")
    p.add_argument("--api-key", dest="api_key", help="Override API key (lebih aman via env)")
    p.add_argument("--approval-mode", choices=sorted(VALID_APPROVAL_MODES), help="smart | always | never")
    p.add_argument("--workspace", help="Override LACTION_WORKSPACE (root file tools)")
    p.add_argument("--sandbox-mode", choices=sorted(VALID_SANDBOX_MODES), help="none | auto | docker")
    p.add_argument("--max-iterations", type=int, help="Batas loop tool per turn")
    p.add_argument("--context-limit", type=int, help="Batas token sebelum kompresi")
    p.add_argument("--session", help="Pakai / lanjutkan session_id tertentu")
    p.add_argument("-v", "--verbose", action="store_true", help="Log debug")


def _new_parser(add_help: bool = True) -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        prog="laction",
        description="Laction Agent — AI agent lokal, Hermes-inspired, zero-dependency.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=add_help,
        epilog=(
            "Contoh:\n"
            "  laction \"list file\"\n"
            "  laction \"ingat: saya suka kopi\"\n"
            "  laction chat\n"
            "  laction gateway --host 0.0.0.0 --port 8000\n\n"
            "Tanpa argumen: masuk mode chat interaktif. Mode default = mock (tanpa API key)."
        ),
    )


def _add_subcommands(p: argparse.ArgumentParser):
    sub = p.add_subparsers(dest="command")

    sub.add_parser("chat", help="Mode interaktif (REPL)")

    run_p = sub.add_parser("run", help="Jalankan satu pesan lalu keluar")
    run_p.add_argument("text", nargs="+", help="Pesan yang dikirim ke agent")

    sub.add_parser("init", help="Inisialisasi profil: MEMORY.md, USER.md, sessions.db, skills/")

    status_p = sub.add_parser("status", help="Tampilkan konfigurasi & state agent")
    status_p.add_argument("--json", action="store_true", help="Output JSON")

    tools_p = sub.add_parser("tools", help="Daftar tool yang terdaftar")
    tools_p.add_argument("--json", action="store_true", help="Output JSON skema tools")

    skills_p = sub.add_parser("skills", help="Daftar / lihat skill")
    skills_p.add_argument("name", nargs="?", help="Nama skill untuk dilihat isinya")
    skills_p.add_argument("--json", action="store_true", help="Output JSON")

    mem_p = sub.add_parser("memory", help="Lihat / tambah / pangkas memory")
    mem_p.add_argument("action", nargs="?", default="show", choices=["show", "add", "user", "prune"])
    mem_p.add_argument("note", nargs="*", help="Catatan untuk action add/user")
    mem_p.add_argument("--max-entries", dest="max_entries", type=int, default=50, help="Batas entri terbaru per file (prune)")
    mem_p.add_argument("--max-chars", dest="max_chars", type=int, default=6000, help="Batas karakter per file (prune)")
    mem_p.add_argument("--target", choices=["all", "memory", "user"], default="all", help="File yang dipangkas")

    traces_p = sub.add_parser("traces", help="Lihat jejak eksekusi tool (observability)")
    traces_p.add_argument("--session", dest="traces_session", help="Filter session_id")
    traces_p.add_argument("--limit", type=int, default=20, help="Jumlah event terbaru (default 20)")
    traces_p.add_argument("--json", action="store_true", help="Output JSON")
    traces_p.add_argument(
        "--keep",
        type=int,
        default=10_000,
        help="Dengan --prune: simpan hanya N event terbaru (default 10000)",
    )
    traces_p.add_argument(
        "--prune",
        action="store_true",
        help="Hapus tool_events lama (riwayat chat tidak disentuh)",
    )

    mcp_p = sub.add_parser("mcp", help="Kelola server MCP (allowlist eksplisit)")
    mcp_sub = mcp_p.add_subparsers(dest="mcp_command")
    mcp_sub.add_parser("list", help="Daftar server terdaftar")
    mcp_add = mcp_sub.add_parser("add", help="Tambah server MCP")
    mcp_add.add_argument("--name", required=True)
    # dest eksplisit: `--command` tidak boleh menimpa dest subcommand `command`.
    mcp_add.add_argument("--command", dest="mcp_server_command", required=True)
    mcp_add.add_argument(
        "--args",
        nargs=argparse.REMAINDER,
        default=[],
        help="Argumen command (taruh paling akhir; boleh mengandung tanda '-')",
    )
    mcp_add.add_argument("--description", default="")
    mcp_add.add_argument(
        "--allow-tools",
        nargs="*",
        default=[],
        help="Allowlist nama tool pada server ini (kosong = semua tool, tetap butuh approval)",
    )
    mcp_rm = mcp_sub.add_parser("remove", help="Hapus server MCP")
    mcp_rm.add_argument("--name", required=True)
    mcp_tools = mcp_sub.add_parser("tools", help="Daftar tool pada satu server (menjalankannya sementara)")
    mcp_tools.add_argument("--name", required=True)
    mcp_allow = mcp_sub.add_parser("allow", help="Batasi tool yang boleh dipanggil pada satu server")
    mcp_allow.add_argument("--name", required=True)
    mcp_allow.add_argument("--tools", nargs="*", default=[], help="Nama tool (kosong = izinkan semua)")

    cron_p = sub.add_parser("cron", help="Kelola tugas terjadwal")
    cron_sub = cron_p.add_subparsers(dest="cron_command")
    cron_sub.add_parser("list", help="Daftar cron job")
    cron_add = cron_sub.add_parser("add", help="Tambah cron job")
    cron_add.add_argument("--name", required=True)
    cron_add.add_argument("--task", required=True)
    cron_add.add_argument("--interval", dest="interval_seconds", type=int, default=3600, help="Detik (min 10)")
    cron_rm = cron_sub.add_parser("remove", help="Hapus cron job")
    cron_rm.add_argument("--name", required=True)
    cron_sub.add_parser("start", help="Jalankan scheduler di foreground")

    gw_p = sub.add_parser("gateway", help="Jalankan UI chat + HTTP API")
    gw_p.add_argument("--host", default="0.0.0.0", help="Default 0.0.0.0 (cocok untuk preview)")
    gw_p.add_argument("--port", type=int, default=int(os.environ.get("LACTION_GATEWAY_PORT", "8000")))
    gw_p.add_argument("--token", help="Token akses (default: LACTION_GATEWAY_TOKEN)")
    gw_p.add_argument("--no-cron", action="store_true", help="Matikan scheduler cron")
    gw_p.add_argument("--cron", action="store_true", help="Paksa scheduler cron aktif")

    sub.add_parser("doctor", help="Cek kesehatan instalasi & konfigurasi")
    return sub


def build_message_parser() -> argparse.ArgumentParser:
    """Parser untuk one-shot / REPL: tidak punya subcommand sama sekali."""
    p = _new_parser()
    _add_global_args(p)
    p.add_argument("message", nargs="*", help="Pesan one-shot (jika tidak ada subcommand)")
    return p


def build_subcommand_parser() -> argparse.ArgumentParser:
    """Parser untuk perintah eksplisit: tidak punya positional `message`."""
    p = _new_parser()
    _add_global_args(p)
    _add_subcommands(p)
    return p


def build_parser() -> argparse.ArgumentParser:
    """Parser gabungan untuk keperluan --help / inspeksi."""
    p = _new_parser()
    _add_global_args(p)
    p.add_argument("message", nargs="*", help="Pesan one-shot (jika tidak ada subcommand)")
    _add_subcommands(p)
    return p


_GLOBAL_OPTS_WITH_VALUE = {
    "--config", "--home", "--provider", "--model", "--api-base", "--api-key",
    "--approval-mode", "--max-iterations", "--context-limit", "--session",
    "--workspace", "--sandbox-mode",
}
_GLOBAL_FLAGS = {"-v", "--verbose", "--version"}


def _hoist_global_options(raw: list[str]) -> list[str]:
    """Pindahkan opsi global ke depan agar boleh ditulis sesudah subcommand.

    Tanpa ini `laction status --home ./data` gagal, karena subparser tidak
    mewarisi opsi root. Meng-copy opsi ke tiap subparser berisiko menimpa
    nilai root dengan default `None`, jadi argv yang dirapikan saja.
    `--help` sengaja dibiarkan di tempatnya supaya help subcommand tetap benar.
    """
    globals_: list[str] = []
    rest: list[str] = []
    i = 0
    while i < len(raw):
        token = raw[i]
        if token in _GLOBAL_OPTS_WITH_VALUE:
            globals_.append(token)
            if i + 1 < len(raw):
                globals_.append(raw[i + 1])
                i += 1
        elif any(token.startswith(opt + "=") for opt in _GLOBAL_OPTS_WITH_VALUE):
            globals_.append(token)
        elif token in _GLOBAL_FLAGS:
            globals_.append(token)
        else:
            rest.append(token)
        i += 1
    return globals_ + rest


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Router dua tahap: bedakan `laction list file` vs `laction status --json`.

    Argparse tidak bisa dengan aman menggabungkan `message nargs='*'` dan
    subparsers dalam satu parser (kata kedua pesan bisa tertukar jadi
    subcommand). Kita rapikan opsi global, konsumsi lewat router, lalu pilih
    parser yang tepat. Parser terpilih tetap memvalidasi ulang seluruh argv.
    """
    raw = _hoist_global_options(list(sys.argv[1:] if argv is None else argv))

    router = argparse.ArgumentParser(add_help=False)
    _add_global_args(router)
    _ns, rest = router.parse_known_args(raw)

    if "-h" in raw or "--help" in raw:
        if rest and rest[0] in KNOWN_COMMANDS:
            return build_subcommand_parser().parse_args(raw)
        return build_message_parser().parse_args(raw)

    if rest and rest[0] in KNOWN_COMMANDS:
        return build_subcommand_parser().parse_args(raw)
    if rest and rest[0].startswith("-"):
        # Opsi tidak dikenal: biarkan parser pesan yang memberi error rapi.
        return build_message_parser().parse_args(raw)

    args = build_message_parser().parse_args(raw)
    args.command = None
    return args


def resolve_config(args: argparse.Namespace) -> Config:
    cfg = Config.load(args.config)
    overrides = {
        "home": args.home,
        "provider": args.provider,
        "model": args.model,
        "api_base": args.api_base,
        "api_key": args.api_key,
        "approval_mode": args.approval_mode,
        "max_iterations": args.max_iterations,
        "context_limit": args.context_limit,
        "workspace": getattr(args, "workspace", None),
        "sandbox_mode": getattr(args, "sandbox_mode", None),
    }
    for attr, value in overrides.items():
        if value is not None:
            setattr(cfg, attr, value)
    cfg.validate()
    logging.getLogger().setLevel(logging.DEBUG if args.verbose else logging.INFO)
    logging.getLogger("laction").setLevel(logging.DEBUG if args.verbose else logging.INFO)
    return cfg


def _approval_prompt(command: str) -> bool:
    print(f"\n⚠️  Persetujuan diperlukan untuk menjalankan:\n    {command}")
    try:
        answer = input("    Jalankan? [y/N] ").strip().lower()
    except EOFError:
        return False
    return answer in ("y", "ya", "yes")


def make_agent(cfg: Config, args: argparse.Namespace, interactive: bool = False) -> AIAgent:
    agent = AIAgent(
        cfg,
        session_id=getattr(args, "session", None) or None,
        approve=_approval_prompt if interactive else None,
    )
    return agent


def _print_banner(cfg: Config, agent: AIAgent):
    print("🛰️  Laction Agent v" + __version__)
    print(f"   provider={cfg.provider}  model={cfg.model}  session={agent.session_id}")
    print(f"   home={Path(cfg.home).expanduser().resolve()}  tools={len(get_registry().schemas())}")
    print(f"   workspace={Path(cfg.workspace or Path.cwd()).expanduser().resolve()}  sandbox={cfg.sandbox_mode}")
    for warning in cfg.warnings():
        print(f"   ⚠️  {warning}")
    print("   Ketik /help, /tools, /skills, /memory, /traces, /status, /new, /exit")
    print()


def one_shot(cfg: Config, args: argparse.Namespace, text: str) -> int:
    agent = make_agent(cfg, args)
    print(agent.run(text))
    return 0


def interactive_chat(cfg: Config, args: argparse.Namespace) -> int:
    agent = make_agent(cfg, args, interactive=True)
    _print_banner(cfg, agent)

    while True:
        try:
            line = input("🧑 kamu> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nSampai jumpa 👋")
            return 0
        if not line:
            continue

        low = line.lower()
        if low in ("exit", "quit", "keluar", "/exit", "/quit"):
            print("Sampai jumpa 👋")
            return 0

        if line.startswith("/"):
            parts = line.split(maxsplit=1)
            cmd = parts[0].lower()
            rest = parts[1] if len(parts) > 1 else ""
            if cmd == "/help":
                print(
                    "/help  /tools  /skills  /memory  /traces  /status  /session [id]  /new  /clear  "
                    "/cron list  /exit\n"
                    "Atau langsung ketik perintah biasa, mis: list file / ingat: saya suka kopi"
                )
            elif cmd == "/tools":
                print(", ".join(get_registry().names()))
            elif cmd == "/skills":
                print("\n".join(f"- {s['name']}: {s['description']}" for s in agent.skills.list_skills()))
            elif cmd == "/memory":
                print(agent.memory.read_all())
            elif cmd == "/traces":
                _print_traces(agent.db, session_id=agent.session_id, limit=15)
            elif cmd == "/status":
                print(json.dumps(cfg.as_dict(), ensure_ascii=False, indent=2))
                print(f"session={agent.session_id}  tools={len(get_registry().schemas())}")
            elif cmd == "/session":
                if rest:
                    agent = AIAgent(cfg, session_id=rest.strip(), approve=_approval_prompt)
                    print(f"Berpindah ke sesi {agent.session_id}")
                else:
                    print(f"Session saat ini: {agent.session_id}")
            elif cmd in ("/new", "/clear"):
                agent = AIAgent(cfg, approve=_approval_prompt)
                print(f"Sesi baru: {agent.session_id}")
            elif cmd == "/cron" and rest.strip() == "list":
                jobs = CronScheduler(Path(cfg.home)).list_jobs()
                print("\n".join(f"- {j['name']}: {j['task']} ({j['interval_seconds']}s)" for j in jobs) or "(kosong)")
            else:
                print(f"Perintah internal tidak dikenal: {cmd}. Ketik /help.")
            continue

        try:
            reply = agent.run(line)
        except Exception as e:  # noqa: BLE001
            reply = f"ERROR: {e}"
        print(f"\n🤖 laction> {reply}\n")
    return 0


def cmd_status(cfg: Config, args: argparse.Namespace) -> int:
    home = Path(cfg.home).expanduser()
    home.mkdir(parents=True, exist_ok=True)
    mgr = MemoryManager(home)
    db = SessionDB(home)
    skills = SkillManager(home).list_skills()
    tools = get_registry().schemas()
    jobs = CronScheduler(home).list_jobs()
    data = {
        "version": __version__,
        "config": cfg.as_dict(redact=True),
        "home": str(home.resolve()),
        "session_db": str((home / "sessions.db").resolve()),
        "memory_bytes": len(mgr.read_memory()) + len(mgr.read_user()),
        "skills": [s["name"] for s in skills],
        "tools": [t["name"] for t in tools],
        "cron_jobs": jobs,
        "warnings": cfg.warnings(),
        "db_sessions": len({r["session_id"] for r in db.search("", limit=1000)}),
        "workspace": str(Path(cfg.workspace).expanduser().resolve()) if cfg.workspace else str(Path.cwd().resolve()),
        "sandbox_mode": cfg.sandbox_mode,
        "tool_metrics": db.tool_metrics(),
        "db_stats": db.stats(),
        "mcp_servers": [s["name"] for s in MCPRegistry(home).list_servers()],
    }
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0
    print(f"Laction Agent v{__version__} — status")
    print(f"  Provider     : {cfg.provider} / {cfg.model}")
    print(f"  API base     : {cfg.api_base or '(default provider)'}")
    print(f"  API key      : {'tersedia' if cfg.api_key else '- (mode mock tidak butuh)'}")
    print(f"  Home         : {home.resolve()}")
    print(f"  Session DB   : {home / 'sessions.db'}")
    print(f"  Memory       : {data['memory_bytes']} karakter")
    print(f"  Skills       : {len(skills)} ({', '.join(data['skills']) or '-'})")
    print(f"  Tools        : {len(tools)}")
    print(f"  Cron jobs    : {len(jobs)}")
    print(f"  Max iterasi  : {cfg.max_iterations} | context limit: {cfg.context_limit}")
    print(f"  Workspace    : {data['workspace']}")
    print(f"  Sandbox      : {cfg.sandbox_mode}")
    print(f"  Approval     : {cfg.approval_mode}")
    metrics = data["tool_metrics"]
    stats = data["db_stats"]
    print(f"  Tool events  : {metrics['total_calls']} panggilan (avg {metrics['avg_duration_ms']} ms)")
    print(
        f"  Session DB   : {stats['messages']} pesan / {stats['sessions']} sesi / "
        f"{stats['tool_events']} event ({stats['size_bytes']} byte, FTS5={'ya' if stats['fts_enabled'] else 'tidak'})"
    )
    print(f"  MCP servers  : {len(data['mcp_servers'])} ({', '.join(data['mcp_servers']) or '-'})")
    for w in cfg.warnings():
        print(f"  ⚠️  {w}")
    return 0


def cmd_tools(args: argparse.Namespace) -> int:
    tools = get_registry().schemas()
    if args.json:
        print(json.dumps(tools, ensure_ascii=False, indent=2))
        return 0
    for t in tools:
        print(f"  {t['name']:<16} {t['description']}")
    return 0


def cmd_skills(cfg: Config, args: argparse.Namespace) -> int:
    mgr = SkillManager(Path(cfg.home))
    if args.name:
        content = mgr.view_skill(args.name)
        if content is None:
            print(f"Skill tidak ditemukan: {args.name}", file=sys.stderr)
            return 1
        print(content)
        return 0
    skills = mgr.list_skills()
    if args.json:
        print(json.dumps(skills, ensure_ascii=False, indent=2))
        return 0
    for s in skills:
        print(f"  {s['name']:<20} {s['description']}")
    return 0


def cmd_memory(cfg: Config, args: argparse.Namespace) -> int:
    mgr = MemoryManager(Path(cfg.home))
    if args.action == "show":
        print(mgr.read_all())
        return 0
    if args.action == "prune":
        try:
            stats = mgr.prune(
                max_entries=getattr(args, "max_entries", 50),
                max_chars=getattr(args, "max_chars", 6000),
                target=getattr(args, "target", "all"),
            )
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 2
        print(f"🧹 Memory dipangkas ({stats['target']}): "
              f"{stats['before_chars']} → {stats['after_chars']} karakter, "
              f"{stats['removed_entries']} entri dibuang/diduplikasi.")
        for name, detail in stats["files"].items():
            print(f"   {name:<7} {detail['before_entries']} → {detail['after_entries']} entri")
        return 0
    note = " ".join(args.note).strip()
    if not note:
        print("Catatan tidak boleh kosong. Contoh: laction memory add saya suka kopi", file=sys.stderr)
        return 2
    if args.action == "user":
        stored = mgr.append_user(note)
    else:
        stored = mgr.append_memory(note)
    target_file = "USER.md" if args.action == "user" else "MEMORY.md"
    if not stored:
        print("Catatan tidak boleh kosong.", file=sys.stderr)
        return 2
    flag = " [kredensial disamarkan]" if stored != " ".join(note.splitlines()).strip() else ""
    print(f"Tersimpan ke {target_file}: {stored}{flag}")
    return 0


def _print_traces(db: SessionDB, session_id: str | None = None, limit: int = 20) -> None:
    metrics = db.tool_metrics(session_id)
    events = db.tool_events(session_id, limit=limit)
    print(
        f"📊 Tool events: {metrics['total_calls']} total, avg {metrics['avg_duration_ms']} ms, "
        f"max {metrics['max_duration_ms']} ms"
    )
    if metrics["by_status"]:
        print("   status: " + ", ".join(f"{k}={v}" for k, v in sorted(metrics["by_status"].items())))
    if metrics["by_tool"]:
        print("   per tool:")
        for row in metrics["by_tool"][:10]:
            print(f"     - {row['tool']:<18} {row['calls']:>3}x  avg {row['avg_ms']} ms  non-ok {row['non_ok']}")
    if not events:
        print("   (belum ada event)")
        return
    print("   event terbaru:")
    for ev in events:
        print(f"     [{ev['created_at']}] {ev['tool_name']:<18} {ev['status']:<16} {ev['duration_ms']:>5} ms")


def cmd_traces(cfg: Config, args: argparse.Namespace) -> int:
    db = SessionDB(Path(cfg.home).expanduser())
    sid = getattr(args, "traces_session", None) or getattr(args, "session", None) or None
    limit = max(1, min(int(getattr(args, "limit", 20) or 20), 200))
    if getattr(args, "prune", False):
        result = db.prune_tool_events(keep=getattr(args, "keep", 10_000))
        message = (
            f"🧹 tool_events: {result['before']} → {result['after']} "
            f"(dihapus {result['deleted']}, simpan {result['keep']})"
        )
        if args.json:
            print(json.dumps({**result, "message": message}, ensure_ascii=False, indent=2))
        else:
            print(message)
        return 0
    if args.json:
        print(json.dumps({
            "session_id": sid,
            "metrics": db.tool_metrics(sid),
            "events": db.tool_events(sid, limit=limit),
        }, ensure_ascii=False, indent=2))
        return 0
    _print_traces(db, session_id=sid, limit=limit)
    return 0


def cmd_mcp(cfg: Config, args: argparse.Namespace) -> int:
    registry = MCPRegistry(Path(cfg.home).expanduser())
    command = getattr(args, "mcp_command", None) or "list"

    if command == "list":
        servers = registry.list_servers()
        if not servers:
            print(f"Belum ada server MCP. File: {registry.path}")
            print("Contoh: laction mcp add --name demo --command python3 "
                  "--args -m laction_agent.mcp.demo_server")
            return 0
        for server in servers:
            state = "enabled" if server["enabled"] else "disabled"
            print(f"  {server['name']:<12} [{state}] {server['command']} {' '.join(server['args'])}")
            if server.get("tools"):
                print(f"               tools: {', '.join(server['tools'])}")
            if server.get("description"):
                print(f"               {server['description']}")
        print(f"File: {registry.path}")
        return 0

    if command == "add":
        raw_args = list(getattr(args, "args", []) or [])
        description = getattr(args, "description", "") or ""
        allowed_tools = list(getattr(args, "allow_tools", []) or [])

        # `--args` memakai REMAINDER agar bisa memuat token berawalan '-' seperti
        # `-m`. Konsekuensinya opsi CLI yang ditulis SESUDAH --args ikut tertelan;
        # di sini opsi itu dikeluarkan lagi supaya tidak menjadi argumen server.
        def _extract(flag: str) -> list[str]:
            nonlocal raw_args
            if flag not in raw_args:
                return []
            idx = raw_args.index(flag)
            tail = raw_args[idx + 1:]
            values: list[str] = []
            for token in tail:
                if token.startswith("--"):
                    break
                values.append(token)
            raw_args = raw_args[:idx] + tail[len(values):]
            return values

        extracted_desc = _extract("--description")
        if extracted_desc and not description:
            description = " ".join(extracted_desc)
        extracted_tools = _extract("--allow-tools")
        if extracted_tools:
            allowed_tools = extracted_tools
        try:
            server = registry.add_server(
                name=args.name,
                command=args.mcp_server_command,
                args=raw_args,
                description=description,
                tools=allowed_tools,
            )
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 2
        print(f"✅ Server MCP '{server['name']}' ditambahkan ({server['command']}).")
        allowed = server.get("tools") or []
        if allowed:
            print(f"   Allowlist tool: {', '.join(allowed)}")
        else:
            print("   Allowlist tool: semua tool server (disarankan dibatasi dengan --allow-tools).")
        print("   Tool MCP tetap memerlukan approval setiap pemanggilan.")
        return 0

    if command == "remove":
        removed = registry.remove_server(args.name)
        print(f"🗑️  Server MCP '{args.name}' {'dihapus' if removed else 'tidak ditemukan'}.")
        return 0 if removed else 1

    if command == "tools":
        server = registry.get(args.name)
        if server is None:
            print(f"Server MCP tidak ditemukan: {args.name}", file=sys.stderr)
            return 1
        if not server["enabled"]:
            print(f"Server MCP '{args.name}' dinonaktifkan.", file=sys.stderr)
            return 1
        try:
            with MCPStdioClient(server["command"], server["args"], server["env"], timeout=20) as client:
                info = client.initialize()
                tools = client.list_tools()
        except MCPError as e:
            print(f"ERROR MCP: {e}", file=sys.stderr)
            return 1
        print(f"Server {server['name']} — {info.get('serverInfo', {}).get('name', '?')} "
              f"(protocol {info.get('protocolVersion')})")
        for tool in tools:
            print(f"  {tool['name']:<20} {tool['description']}")
        return 0

    if command == "allow":
        names = list(getattr(args, "tools", None) or [])
        if not registry.set_tools(args.name, names):
            print(f"Server MCP tidak ditemukan: {args.name}", file=sys.stderr)
            return 1
        print(
            f"🔐 '{args.name}' allowlist: " + (", ".join(names) if names else "semua tool server")
        )
        return 0

    print(f"Subcommand mcp tidak dikenal: {command}", file=sys.stderr)
    return 2


def cmd_init(cfg: Config, args: argparse.Namespace) -> int:
    agent = make_agent(cfg, args)
    home = Path(cfg.home).expanduser().resolve()
    print(f"✅ Profil siap di {home}")
    print(f"   session={agent.session_id}")
    print("   dibuat: MEMORY.md, USER.md, sessions.db, skills/")
    print("   skill bawaan: " + ", ".join(s["name"] for s in agent.skills.list_skills()))
    return 0


def _cron_scheduler(cfg: Config) -> CronScheduler:
    def _run(task: str) -> str:
        log.info("Cron run: %s", task[:80])
        return AIAgent(cfg, allowed_tools=READ_ONLY_TOOLS).run(f"[cron] {task}")

    return CronScheduler(Path(cfg.home), on_run=_run)


def cmd_cron(cfg: Config, args: argparse.Namespace) -> int:
    sched = _cron_scheduler(cfg)
    command = args.cron_command or "list"
    if command == "list":
        jobs = sched.list_jobs()
        print("\n".join(f"- {j['name']}: {j['task']} (tiap {j['interval_seconds']}s)" for j in jobs) or "(tidak ada cron job)")
        return 0
    if command == "add":
        sched.add_job(args.name, args.task, max(10, args.interval_seconds))
        print(f"✅ Cron '{args.name}' ditambahkan.")
        return 0
    if command == "remove":
        sched.remove_job(args.name)
        print(f"🗑️  Cron '{args.name}' dihapus (bila ada).")
        return 0
    if command == "start":
        jobs = sched.list_jobs()
        print(f"⏰ Cron aktif di {Path(cfg.home).resolve()} — {len(jobs)} job. Ctrl+C untuk berhenti.")
        sched.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nCron dihentikan.")
        finally:
            sched.stop()
        return 0
    print(f"Subcommand cron tidak dikenal: {command}", file=sys.stderr)
    return 2


def cmd_gateway(cfg: Config, args: argparse.Namespace) -> int:
    if run_server is None:
        print("Gateway tidak tersedia (import gagal).", file=sys.stderr)
        return 1
    if args.no_cron:
        cfg.cron_enabled = False
    if args.cron:
        cfg.cron_enabled = True
    token = args.token or os.environ.get("LACTION_GATEWAY_TOKEN") or None
    try:
        run_server(cfg, host=args.host, port=args.port, token=token)
    except OSError as e:
        print(f"Gagal bind {args.host}:{args.port}: {e}", file=sys.stderr)
        return 1
    return 0


def cmd_doctor(cfg: Config) -> int:
    checks: list[tuple[str, bool, str]] = []
    checks.append(("Python >= 3.11", sys.version_info >= (3, 11), ".".join(map(str, sys.version_info[:3]))))
    checks.append(("Config valid", True, cfg.provider))
    checks.append(("Tool registry", len(get_registry().schemas()) >= 10, f"{len(get_registry().schemas())} tools"))

    try:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            mgr = MemoryManager(home)
            mgr.append_memory("doctor check")
            db = SessionDB(home)
            sid = db.new_session()
            db.save(sid, "user", "doctor check")
            ok_memory = "doctor check" in mgr.read_memory() and bool(db.search("doctor check"))
            skills = SkillManager(home).list_skills()
        checks.append(("Memory + SQLite", ok_memory, "MEMORY.md & sessions.db writable"))
        checks.append(("Skill bawaan", len(skills) >= 13, f"{len(skills)} skill"))
    except Exception as e:  # noqa: BLE001
        checks.append(("Memory + SQLite", False, str(e)))
        checks.append(("Skill bawaan", False, "gagal dibaca"))

    checks.append(("Gateway module", run_server is not None, "laction_agent.gateway"))

    # Regresi hasil review: guard keamanan harus ikut teruji di `doctor`.
    checks.append((
        "Redaksi secret",
        "rahasia-banget-123" not in redact("api_key=rahasia-banget-123"),
        "token & key=value tersamarkan",
    ))
    checks.append((
        "Terminal guard",
        _is_dangerous("echo aman; curl https://x") and not _is_dangerous("echo aman"),
        "chain & substitusi terdeteksi",
    ))
    checks.append((
        "SSRF guard",
        _is_blocked_url("http://169.254.169.254/latest/meta-data/", allow_private=False)
        and not _is_blocked_url("https://8.8.8.8/", allow_private=False),
        "privat/link-local diblokir",
    ))
    python_guard = get_registry().call(
        "run_python", {"code": "print('doctor')"}, context={"approval_mode": "smart"}
    )
    checks.append(("Python approval", "PERLU APPROVAL" in python_guard or "DITOLAK" in python_guard, "arbitrary code fail-closed tanpa callback"))
    rag_guard = get_registry().call("rag_search", {"query": "doctor", "path": "../"})
    checks.append(("RAG path guard", "DITOLAK" in rag_guard, "retrieval dibatasi ke workspace"))

    # Paket A: FTS5, prune, dan redaksi terpusat.
    try:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            db = SessionDB(home)
            sid = db.new_session()
            db.save(sid, "user", "pencarian peringkat unik-xyz")
            hits = db.search("unik-xyz")
            checks.append((
                "FTS5 search",
                bool(hits) or db.fts_enabled is False,
                "BM25 aktif" if db.fts_enabled else "fallback LIKE (FTS5 tidak tersedia)",
            ))
            checks.append((
                "Search empty query",
                isinstance(db.search("", limit=5), list),
                "kueri kosong aman",
            ))
            mgr = MemoryManager(home)
            for i in range(30):
                mgr.append_memory(f"catatan {i}")
            stats = mgr.prune(max_entries=5, max_chars=1000)
            checks.append((
                "Memory prune",
                len(mgr.read_memory().splitlines()) <= 8 and stats["removed_entries"] > 0,
                f"{stats['before_chars']} → {stats['after_chars']} karakter",
            ))
            mgr.append_memory("nilai api_key=rahasia-prune-999")
            checks.append((
                "Redaksi memory",
                "rahasia-prune-999" not in mgr.read_memory(),
                "CLI & gateway menulis lewat redact()",
            ))
            db.record_tool_event(sid, "read_file", "ok", 12, "{}", "ok")
            metrics = db.tool_metrics(sid)
            checks.append((
                "Tool events",
                metrics["total_calls"] == 1 and metrics["by_status"].get("ok") == 1,
                "sessions.db menyimpan jejak tool",
            ))
    except Exception as e:  # noqa: BLE001
        checks.append(("Memory v2 + FTS5", False, str(e)))

    # Paket C: workspace eksplisit & backend sandbox.
    try:
        from .tools import file_tools

        ws = file_tools.get_workspace({"cfg": cfg})
        checks.append(("Workspace eksplisit", isinstance(ws, Path) and ws.is_absolute(), str(ws)))
    except Exception as e:  # noqa: BLE001
        checks.append(("Workspace eksplisit", False, str(e)))
    backend, _backend_err = resolve_execution_backend(cfg.sandbox_mode)
    docker_ok = backend != "blocked"
    checks.append((
        "Sandbox backend",
        docker_ok,
        f"mode={cfg.sandbox_mode} → {backend}" + (
            " (Docker siap)" if backend == "docker" else ""
        ),
    ))
    if cfg.sandbox_mode in {"docker", "auto"}:
        checks.append((
            "Docker daemon",
            DockerExecutor.is_daemon_ready() or cfg.sandbox_mode == "auto",
            "perlu untuk sandbox_mode=docker",
        ))

    # Paket D: registry MCP + roundtrip server demo.
    try:
        with tempfile.TemporaryDirectory() as tmp:
            registry = MCPRegistry(Path(tmp))
            registry.add_server("demo", sys.executable, ["-m", "laction_agent.mcp.demo_server"])
            checks.append(("MCP registry", registry.get("demo") is not None, "allowlist mcp_servers.json"))
            server = registry.get("demo")
            with MCPStdioClient(server["command"], server["args"], server["env"], timeout=15) as client:
                client.initialize()
                tools = {t["name"] for t in client.list_tools()}
                pong = client.call_tool("ping", {"message": "doctor"})
            checks.append((
                "MCP stdio client",
                {"ping", "workspace_summary"} <= tools and "pong" in pong,
                f"{len(tools)} tool demo",
            ))
    except Exception as e:  # noqa: BLE001
        checks.append(("MCP stdio client", False, str(e)))

    # Hardening: SQLite WAL/pemulihan, allowlist tool MCP, retensi observability.
    try:
        with tempfile.TemporaryDirectory() as tmp:
            db = SessionDB(Path(tmp))
            with db._connect() as conn:
                journal = str(conn.execute("PRAGMA journal_mode").fetchone()[0]).lower()
            checks.append(("SQLite WAL", journal == "wal", f"journal_mode={journal}"))

            sid = db.new_session()
            for i in range(6):
                db.record_tool_event(sid, f"t{i}", "ok", i, "{}", "ok")
            db.save(sid, "user", "riwayat tetap")
            pruned = db.prune_tool_events(keep=2)
            checks.append((
                "Retensi tool_events",
                pruned["after"] == 2 and bool(db.search("riwayat")),
                f"{pruned['before']} → {pruned['after']} event, chat utuh",
            ))
    except Exception as e:  # noqa: BLE001
        checks.append(("SQLite WAL", False, str(e)))

    try:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "sessions.db"
            db_path.write_bytes(b"bukan sqlite" * 64)
            recovered = SessionDB(Path(tmp))
            checks.append((
                "DB korup dipulihkan",
                bool(recovered.recovered_from) and Path(recovered.recovered_from).exists(),
                "dikarantina lalu dibuat ulang",
            ))
            registry = MCPRegistry(Path(tmp))
            registry.add_server("demo", sys.executable, ["-m", "laction_agent.mcp.demo_server"], tools=["ping"])
            checks.append((
                "MCP allowlist tool",
                registry.get("demo")["tools"] == ["ping"],
                "tool di luar daftar ditolak sebelum approval",
            ))
    except Exception as e:  # noqa: BLE001
        checks.append(("DB korup dipulihkan", False, str(e)))

    if cfg.provider == "mock":
        checks.append(("API key", True, "tidak dibutuhkan (mock)"))
    else:
        checks.append(("API key", bool(cfg.api_key), "tersedia" if cfg.api_key else "LACTION_API_KEY kosong"))

    print("🩺 Laction Doctor")
    failed = 0
    for name, ok, detail in checks:
        print(f"  {'✅' if ok else '❌'} {name:<20} {detail}")
        failed += 0 if ok else 1
    for w in cfg.warnings():
        print(f"  ⚠️  {w}")
    print("Semua check lulus." if failed == 0 else f"{failed} check gagal.")
    return 0 if failed == 0 else 1


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        cfg = resolve_config(args)
    except ValueError as e:
        print(f"Konfigurasi error: {e}", file=sys.stderr)
        return 2

    try:
        command = args.command
        if command == "chat":
            return interactive_chat(cfg, args)
        if command == "run":
            return one_shot(cfg, args, " ".join(args.text))
        if command == "init":
            return cmd_init(cfg, args)
        if command == "status":
            return cmd_status(cfg, args)
        if command == "tools":
            return cmd_tools(args)
        if command == "skills":
            return cmd_skills(cfg, args)
        if command == "memory":
            return cmd_memory(cfg, args)
        if command == "traces":
            return cmd_traces(cfg, args)
        if command == "mcp":
            return cmd_mcp(cfg, args)
        if command == "cron":
            return cmd_cron(cfg, args)
        if command == "gateway":
            return cmd_gateway(cfg, args)
        if command == "doctor":
            return cmd_doctor(cfg)
        if getattr(args, "message", None):
            return one_shot(cfg, args, " ".join(args.message))
        return interactive_chat(cfg, args)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
