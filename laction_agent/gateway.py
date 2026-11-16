"""
Gateway HTTP — surface web untuk Laction Agent (stdlib `http.server`).

Endpoint:
- `GET  /`               UI chat (vanilla HTML/JS, relatif URL saja)
- `GET  /health`         status ringan
- `GET  /config`         konfigurasi (API key disamarkan)
- `GET  /tools`          skema tools
- `GET  /skills`         daftar skill
- `GET  /memory`         MEMORY.md + USER.md
- `GET  /history?sid=`   riwayat sesi
- `GET  /cron`           daftar cron job
- `GET  /traces?sid=`    tool events + metrics (observability)
- `GET  /mcp`            server MCP terdaftar (allowlist + allowlist per-tool)
- `POST /mcp`            {name} -> uji koneksi server (initialize + tools/list)
- `POST /chat`           {message, session_id?} -> {reply, session_id}
- `POST /cron`           {name, task, interval_seconds}
- `POST /memory`         {note, target: memory|user} atau {action:"prune", ...}
- `POST /reset`          {session_id?} -> buang agent dari memori

Keamanan: opsional `LACTION_GATEWAY_TOKEN` (Bearer / X-Laction-Token).
Tanpa token, jangan ekspos gateway langsung ke internet publik.
"""
from __future__ import annotations

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import __version__
from .agent import AIAgent
from .policies import READ_ONLY_TOOLS
from .config import Config
from .cron.scheduler import CronScheduler
from .memory.manager import MemoryManager
from .memory.session_db import SessionDB
from .mcp.client import MCPError, MCPStdioClient
from .mcp.registry import MCPRegistry
from .skills.manager import SkillManager
from .tools.registry import get_registry
from .utils import log, redact

STARTED_AT = time.monotonic()

HTML = r"""<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Laction Agent</title>
<style>
  :root { color-scheme: dark; --bg:#0b1020; --panel:#121a30; --line:#263355; --txt:#e8edf7; --muted:#93a2c4; --accent:#6ee7b7; --user:#1e3a5f; --bot:#17233c; }
  * { box-sizing: border-box; }
  body { margin:0; font:14px/1.5 ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif; background:var(--bg); color:var(--txt); }
  header { display:flex; align-items:center; justify-content:space-between; padding:14px 20px; border-bottom:1px solid var(--line); background:#0e162b; }
  header h1 { margin:0; font-size:17px; letter-spacing:.2px; }
  .badge { font-size:12px; color:var(--muted); border:1px solid var(--line); padding:5px 10px; border-radius:999px; }
  .app { display:grid; grid-template-columns:minmax(0,1fr) 300px; gap:16px; padding:16px; max-width:1200px; margin:0 auto; }
  @media (max-width:820px){ .app{grid-template-columns:1fr} aside{order:-1} }
  section, aside { background:var(--panel); border:1px solid var(--line); border-radius:14px; overflow:hidden; }
  .log { height:min(68vh,620px); overflow:auto; padding:16px; display:flex; flex-direction:column; gap:10px; }
  .msg { padding:10px 13px; border-radius:12px; white-space:pre-wrap; word-break:break-word; max-width:88%; }
  .msg.user { align-self:flex-end; background:var(--user); }
  .msg.assistant { align-self:flex-start; background:var(--bot); border:1px solid var(--line); }
  .msg.system { align-self:center; color:var(--muted); font-size:12px; }
  form { display:flex; gap:10px; padding:12px; border-top:1px solid var(--line); background:#0f1830; }
  textarea { flex:1; resize:vertical; min-height:46px; max-height:140px; padding:11px; border-radius:10px; border:1px solid var(--line); background:#0a1226; color:var(--txt); font:inherit; }
  button { cursor:pointer; border:1px solid var(--line); background:#1b2a4a; color:var(--txt); border-radius:10px; padding:9px 13px; font:inherit; }
  button.primary { background:var(--accent); color:#052018; border-color:var(--accent); font-weight:700; }
  button:hover { filter:brightness(1.12); }
  aside { padding:14px; }
  aside h3 { margin:14px 0 6px; font-size:12px; text-transform:uppercase; letter-spacing:.08em; color:var(--muted); }
  aside input { width:100%; padding:8px 10px; border-radius:9px; border:1px solid var(--line); background:#0a1226; color:var(--txt); font:inherit; }
  .row { display:flex; gap:8px; }
  .row > * { flex:1; }
  .btns { display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-top:8px; }
  pre { margin:10px 0 0; padding:10px; max-height:240px; overflow:auto; background:#081026; border:1px solid var(--line); border-radius:10px; color:#bcd0f5; font-size:11px; white-space:pre-wrap; }
  code { color:var(--accent); }
</style>
</head>
<body>
<header>
  <h1>🛰️ Laction Agent <span style="color:var(--muted);font-weight:400">/ gateway</span></h1>
  <span class="badge" id="status">memeriksa…</span>
</header>
<div class="app">
  <section>
    <div class="log" id="log"></div>
    <form id="form">
      <textarea id="msg" placeholder="Tulis perintah… contoh: list file, ingat: saya suka kopi, delegasikan: list skill" autofocus></textarea>
      <button class="primary" type="submit">Kirim ↵</button>
    </form>
  </section>
  <aside>
    <h3>Sesi</h3>
    <input id="session" placeholder="(sesi baru)" autocomplete="off">
    <div class="btns" style="margin-top:8px">
      <button id="new">Sesi baru</button>
      <button id="reset">Reset</button>
    </div>
    <h3>Token <span style="text-transform:none">(opsional)</span></h3>
    <input id="token" type="password" placeholder="LACTION_GATEWAY_TOKEN" autocomplete="off">
    <h3>Inspeksi</h3>
    <div class="btns">
      <button data-get="/tools">Tools</button>
      <button data-get="/skills">Skills</button>
      <button data-get="/memory">Memory</button>
      <button data-get="/cron">Cron</button>
      <button data-get="/traces">Traces</button>
      <button data-get="/mcp">MCP</button>
    </div>
    <div class="btns" style="margin-top:8px">
      <button id="prune">Prune memory</button>
    </div>
    <pre id="panel">Klik tombol inspeksi untuk melihat state agent.</pre>
    <p style="color:var(--muted);font-size:11px;margin-bottom:0">
      Mode <code>mock</code> jalan tanpa API key. Semua URL bersifat relatif sehingga aman dipakai lewat preview proxy.
    </p>
  </aside>
</div>
<script>
const logEl = document.getElementById('log');
const msgEl = document.getElementById('msg');
const form = document.getElementById('form');
const sessionEl = document.getElementById('session');
const tokenEl = document.getElementById('token');
const panel = document.getElementById('panel');
const statusEl = document.getElementById('status');

let sessionId = localStorage.getItem('laction_session') || '';
tokenEl.value = localStorage.getItem('laction_token') || '';
sessionEl.value = sessionId;

function bubble(role, text) {
  const div = document.createElement('div');
  div.className = 'msg ' + role;
  div.textContent = text;
  logEl.appendChild(div);
  logEl.scrollTop = logEl.scrollHeight;
  return div;
}
function headers() {
  const t = tokenEl.value.trim();
  return {'Content-Type': 'application/json', ...(t ? {'Authorization': 'Bearer ' + t} : {})};
}
async function api(path, opts = {}) {
  const res = await fetch(path, {...opts, headers: {...headers(), ...(opts.headers || {})}});
  let data = {};
  try { data = await res.json(); } catch (e) {}
  if (!res.ok) throw new Error(data.error || ('HTTP ' + res.status));
  return data;
}
bubble('system', 'Laction Agent siap. Ketik /help di CLI untuk daftar perintah, atau coba "list file".');

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const message = msgEl.value.trim();
  if (!message) return;
  bubble('user', message);
  msgEl.value = '';
  const pending = bubble('assistant', 'Menjalankan…');
  try {
    const data = await api('/chat', {method: 'POST', body: JSON.stringify({message, session_id: sessionId})});
    sessionId = data.session_id || '';
    sessionEl.value = sessionId;
    localStorage.setItem('laction_session', sessionId);
    pending.textContent = data.reply;
  } catch (err) {
    pending.textContent = 'ERROR: ' + err.message;
  }
  logEl.scrollTop = logEl.scrollHeight;
});

msgEl.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); }
});
sessionEl.addEventListener('change', () => {
  sessionId = sessionEl.value.trim();
  localStorage.setItem('laction_session', sessionId);
  bubble('system', 'Berpindah ke sesi: ' + (sessionId || '(baru)'));
});
tokenEl.addEventListener('change', () => localStorage.setItem('laction_token', tokenEl.value.trim()));
document.getElementById('new').onclick = () => {
  sessionId = ''; sessionEl.value = ''; localStorage.removeItem('laction_session');
  logEl.innerHTML = ''; bubble('system', 'Sesi baru dimulai.');
};
document.getElementById('reset').onclick = async () => {
  try { await api('/reset', {method:'POST', body: JSON.stringify({session_id: sessionId})}); bubble('system','Agent sesi ini di-reset.'); }
  catch (e) { bubble('system', 'Reset gagal: ' + e.message); }
};
document.querySelectorAll('[data-get]').forEach(btn => {
  btn.onclick = async () => {
    try { panel.textContent = JSON.stringify(await api(btn.dataset.get), null, 2); }
    catch (e) { panel.textContent = 'ERROR: ' + e.message; }
  };
});
document.getElementById('prune').onclick = async () => {
  try {
    const r = await api('/memory', {method:'POST', body: JSON.stringify({action:'prune', max_entries:50, max_chars:6000, target:'all'})});
    panel.textContent = JSON.stringify(r, null, 2);
    bubble('system', 'Memory dipangkas.');
  } catch (e) { panel.textContent = 'ERROR: ' + e.message; }
};
api('/health').then(d => {
  statusEl.textContent = d.provider + ' · ' + d.model + ' · ' + d.tools + ' tools · v' + d.version;
}).catch(e => { statusEl.textContent = 'offline: ' + e.message; });
</script>
</body>
</html>
"""


MAX_AGENT_SESSIONS = 32
RUN_LOCK_TIMEOUT = 120.0


def _json_default(obj):
    return str(obj)


class _LactionHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def make_handler(
    cfg: Config,
    token: str | None,
    agents: dict[str, AIAgent],
    agents_lock: threading.Lock,
    run_lock: threading.Lock,
    scheduler: CronScheduler | None,
):
    home = Path(cfg.home).expanduser()

    class Handler(BaseHTTPRequestHandler):
        server_version = f"LactionAgent/{__version__}"

        def _send(self, status: int, payload, content_type: str = "application/json; charset=utf-8"):
            if isinstance(payload, (dict, list)):
                body = json.dumps(payload, ensure_ascii=False, default=_json_default).encode("utf-8")
            elif isinstance(payload, str):
                body = payload.encode("utf-8")
            elif payload is None:
                body = b""
            else:
                body = payload
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Laction-Token")
            self.end_headers()
            if body:
                self.wfile.write(body)

        def _json(self, status: int, obj):
            self._send(status, obj)

        def _authorized(self) -> bool:
            if not token:
                return True
            auth = self.headers.get("Authorization", "")
            custom = self.headers.get("X-Laction-Token", "")
            return auth == f"Bearer {token}" or custom == token

        def _read_json(self):
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return None
            if length > 1_000_000:
                return None
            raw = self.rfile.read(length) if length else b"{}"
            try:
                return json.loads(raw.decode("utf-8") or "{}")
            except (json.JSONDecodeError, UnicodeDecodeError):
                return None

        def _get_agent(self, session_id: str | None) -> AIAgent:
            with agents_lock:
                if session_id and session_id in agents:
                    agent = agents[session_id]
                    # LRU: sesi yang baru dipakai pindah ke urutan terakhir.
                    agents.pop(session_id, None)
                    agents[session_id] = agent
                    return agent
                agent = AIAgent(cfg, session_id=session_id or None)
                agents[agent.session_id] = agent
                # Buang sesi paling lama agar memori gateway tidak tumbuh tanpa batas.
                while len(agents) > MAX_AGENT_SESSIONS:
                    oldest = next(iter(agents))
                    agents.pop(oldest, None)
                return agent

        def do_OPTIONS(self):  # noqa: N802 — nama bawaan BaseHTTPRequestHandler
            self._send(204, None)

        def do_GET(self):  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)

            if path == "/":
                return self._send(200, HTML, "text/html; charset=utf-8")
            if path == "/favicon.ico":
                return self._send(204, None)
            if path == "/health":
                return self._json(200, {
                    "ok": True,
                    "version": __version__,
                    "provider": cfg.provider,
                    "model": cfg.model,
                    "tools": len(get_registry().schemas()),
                    "cron_enabled": cfg.cron_enabled,
                    "sessions_cached": len(agents),
                    "sandbox_mode": cfg.sandbox_mode,
                    "uptime_seconds": int(time.monotonic() - STARTED_AT),
                })
            if not self._authorized():
                return self._json(401, {"error": "Token gateway tidak valid."})

            if path == "/config":
                return self._json(200, {"config": cfg.as_dict(redact=True), "warnings": cfg.warnings()})
            if path == "/tools":
                return self._json(200, {"tools": get_registry().schemas()})
            if path == "/skills":
                return self._json(200, {"skills": SkillManager(home).list_skills()})
            if path == "/memory":
                mgr = MemoryManager(home)
                return self._json(200, {"memory": mgr.read_memory(), "user": mgr.read_user()})
            if path == "/history":
                sid = (query.get("session_id") or query.get("sid") or [""])[0]
                return self._json(200, {"session_id": sid, "history": SessionDB(home).history(sid, limit=50) if sid else []})
            if path == "/cron":
                return self._json(200, {"jobs": (scheduler or CronScheduler(home)).list_jobs()})
            if path == "/traces":
                db = SessionDB(home)
                sid = (query.get("session_id") or query.get("sid") or [""])[0].strip() or None
                try:
                    limit = min(max(int((query.get("limit") or ["50"])[0]), 1), 500)
                except (TypeError, ValueError):
                    limit = 50
                return self._json(200, {
                    "session_id": sid,
                    "metrics": db.tool_metrics(sid),
                    "events": db.tool_events(sid, limit=limit),
                })
            if path == "/mcp":
                mc = MCPRegistry(home)
                return self._json(200, {
                    "servers": mc.list_servers(),
                    "path": str(mc.path),
                    "note": "Allowlist per server; kosong = semua tool server, tetap perlu approval.",
                })
            return self._json(404, {"error": f"Endpoint tidak ditemukan: {path}"})

        def do_POST(self):  # noqa: N802
            path = urlparse(self.path).path
            if not self._authorized():
                return self._json(401, {"error": "Token gateway tidak valid."})
            data = self._read_json()
            if data is None:
                return self._json(400, {"error": "Body harus JSON valid (maks 1 MB)."})

            if path == "/chat":
                message = str(data.get("message") or "").strip()
                if not message:
                    return self._json(400, {"error": "Field 'message' wajib diisi."})
                sid = str(data.get("session_id") or "").strip() or None
                agent = self._get_agent(sid)
                # Lock dengan batas tunggu: satu request lambat tidak boleh
                # menggantung request lain tanpa batas waktu.
                if not run_lock.acquire(timeout=RUN_LOCK_TIMEOUT):
                    return self._json(429, {
                        "error": "Agent masih sibuk menjalankan permintaan lain; coba lagi.",
                        "retry_after_seconds": 5,
                    })
                try:
                    reply = agent.run(message)
                except Exception as e:  # noqa: BLE001
                    log.exception("Gateway /chat error")
                    return self._json(500, {"error": str(e)})
                finally:
                    run_lock.release()
                return self._json(200, {"reply": reply, "session_id": agent.session_id})

            if path == "/cron":
                name = str(data.get("name") or "").strip()
                task = str(data.get("task") or "").strip()
                try:
                    interval = max(10, int(data.get("interval_seconds") or 3600))
                except (TypeError, ValueError):
                    return self._json(400, {"error": "interval_seconds harus angka."})
                if not name or not task:
                    return self._json(400, {"error": "Field 'name' dan 'task' wajib diisi."})
                sched = scheduler or CronScheduler(home)
                sched.add_job(name, task, interval)
                return self._json(200, {"ok": True, "jobs": sched.list_jobs()})

            if path == "/memory":
                mgr = MemoryManager(home)
                action = str(data.get("action") or "add").strip().lower()
                if action == "prune":
                    try:
                        max_entries = int(data.get("max_entries") or 50)
                        max_chars = int(data.get("max_chars") or 6000)
                    except (TypeError, ValueError):
                        return self._json(400, {"error": "max_entries/max_chars harus angka."})
                    target = str(data.get("target") or "all").strip().lower()
                    try:
                        stats = mgr.prune(max_entries=max_entries, max_chars=max_chars, target=target)
                    except ValueError as exc:
                        return self._json(400, {"error": str(exc)})
                    return self._json(200, {"ok": True, "action": "prune", "stats": stats})
                note = str(data.get("note") or "").strip()
                if not note:
                    return self._json(400, {"error": "Field 'note' wajib diisi."})
                target = str(data.get("target") or "memory").lower()
                raw_len = len(redact(note))
                stored = mgr.append_user(note) if target == "user" else mgr.append_memory(note)
                return self._json(200, {
                    "ok": True,
                    "target": target,
                    "stored": stored,
                    "redacted": bool(stored) and stored != " ".join(note.splitlines()).strip(),
                    "visible_chars": raw_len,
                })

            if path == "/mcp":
                # Uji koneksi satu server MCP dari UI, hanya server di allowlist.
                mc = MCPRegistry(home)
                name = str(data.get("name") or "").strip().lower()
                if not name:
                    return self._json(400, {"error": "Field 'name' wajib diisi."})
                server = mc.get(name)
                if server is None:
                    return self._json(404, {"error": f"Server MCP '{name}' tidak ada di allowlist."})
                if not server["enabled"]:
                    return self._json(400, {"error": f"Server MCP '{name}' dinonaktifkan."})
                try:
                    with MCPStdioClient(
                        server["command"], server["args"], server["env"], timeout=20
                    ) as client:
                        info = client.initialize()
                        tools = [t["name"] for t in client.list_tools()]
                except MCPError as exc:
                    return self._json(502, {"error": f"MCP: {exc}"})
                allowed = server.get("tools") or []
                return self._json(200, {
                    "server": name,
                    "info": info,
                    "tools": tools,
                    "allowed": allowed,
                    "blocked": [t for t in tools if allowed and t not in allowed],
                })

            if path == "/reset":
                sid = str(data.get("session_id") or "").strip()
                with agents_lock:
                    if sid:
                        agents.pop(sid, None)
                    else:
                        agents.clear()
                return self._json(200, {"ok": True, "reset": sid or "all"})

            return self._json(404, {"error": f"Endpoint tidak ditemukan: {path}"})

        def log_message(self, fmt: str, *args):
            log.info("HTTP %s - %s", self.address_string(), fmt % args)

    return Handler


def run_server(
    cfg: Config,
    host: str = "0.0.0.0",
    port: int = 8000,
    token: str | None = None,
) -> None:
    token = token or os.environ.get("LACTION_GATEWAY_TOKEN") or None
    home = Path(cfg.home).expanduser()
    home.mkdir(parents=True, exist_ok=True)

    scheduler: CronScheduler | None = None
    if cfg.cron_enabled:
        def _cron_run(task: str) -> str:
            # Sesi terisolasi tiap run agar riwayat cron tidak bercampur dengan chat.
            return AIAgent(cfg, allowed_tools=READ_ONLY_TOOLS).run(f"[cron] {task}")

        scheduler = CronScheduler(home, on_run=_cron_run)
        scheduler.start()

    agents: dict[str, AIAgent] = {}
    agents_lock = threading.Lock()
    run_lock = threading.Lock()
    handler = make_handler(cfg, token, agents, agents_lock, run_lock, scheduler)
    server = _LactionHTTPServer((host, port), handler)
    server.laction_scheduler = scheduler  # type: ignore[attr-defined]
    server.laction_config = cfg  # type: ignore[attr-defined]

    print(f"🛰️  Laction Gateway jalan di http://{host}:{port}  (provider={cfg.provider}, model={cfg.model})")
    if token:
        print("🔒 Token gateway aktif — kirim Authorization: Bearer <token>")
    else:
        print("⚠️  Tanpa token: jangan ekspos langsung ke internet publik.")
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        print("\nMenghentikan gateway…")
    finally:
        server.server_close()
        if scheduler:
            scheduler.stop()
