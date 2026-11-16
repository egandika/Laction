"""Tests for Paket A (memory v2/FTS5), B (tool_events), C (workspace/sandbox/team timeout), D (MCP)."""
from __future__ import annotations

import json
import sys
import tempfile
import urllib.error
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from laction_agent.agent import AIAgent
from laction_agent.cli import parse_args, build_parser
from laction_agent.config import Config
from laction_agent.gateway import HTML
from laction_agent.mcp.client import MCPError, MCPStdioClient
from laction_agent.mcp.registry import MCPRegistry
from laction_agent.memory.manager import MemoryManager
from laction_agent.memory.session_db import SessionDB
from laction_agent.policies import READ_ONLY_TOOLS
from laction_agent.sandbox import DockerExecutor, resolve_execution_backend
from laction_agent.team import MAX_TEAM_TIMEOUT, MIN_TEAM_TIMEOUT, resolve_team_timeout
from laction_agent.tools import file_tools
from laction_agent.tools.registry import get_registry


class MemoryV2Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.mgr = MemoryManager(self.home)

    def tearDown(self):
        self.tmp.cleanup()

    def test_append_redacts_credentials(self):
        stored = self.mgr.append_memory("api_key=super-rahasia-123 dan sk-abcdefghijklmnop")
        text = self.mgr.read_memory()
        self.assertNotIn("super-rahasia-123", text)
        self.assertNotIn("sk-abcdefghijklmnop", text)
        self.assertIn("***", text)
        self.assertIn("***", stored)

    def test_append_user_redacts(self):
        self.mgr.append_user("password: jangan-disimpan-999")
        self.assertNotIn("jangan-disimpan-999", self.mgr.read_user())

    def test_append_enforces_disk_cap_but_read_all_is_not_truncated(self):
        manager = MemoryManager(self.home, max_file_chars=600)
        for i in range(60):
            manager.append_memory(f"catatan panjang nomor {i} " + "x" * 40)
        self.assertLessEqual(manager.memory_file.stat().st_size, 600 + 200)
        self.assertIn("catatan", manager.read_memory())

    def test_prune_keeps_newest_and_dedupes(self):
        for i in range(20):
            self.mgr.append_memory(f"entri {i % 5}")
        stats = self.mgr.prune(max_entries=3, max_chars=5000)
        entries = [line for line in self.mgr.read_memory().splitlines() if line.startswith("- ")]
        self.assertEqual(len(entries), 3)
        self.assertGreater(stats["removed_entries"], 0)
        self.assertIn("entri 4", entries[-1])

    def test_prune_target_validation(self):
        with self.assertRaises(ValueError):
            self.mgr.prune(target="lain")

    def test_prune_single_target(self):
        self.mgr.append_memory("memory satu")
        self.mgr.append_user("user satu")
        stats = self.mgr.prune(max_entries=10, max_chars=1000, target="user")
        self.assertEqual(list(stats["files"]), ["user"])
        self.assertIn("memory satu", self.mgr.read_memory())


class SessionFTS5Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = SessionDB(Path(self.tmp.name))
        self.sid = self.db.new_session()

    def tearDown(self):
        self.tmp.cleanup()

    def test_fts5_available_and_ranked(self):
        self.db.save(self.sid, "user", "kopi tubruk enak sekali")
        self.db.save(self.sid, "assistant", "teh manis juga enak")
        rows = self.db.search("kopi")
        self.assertEqual(len(rows), 1)
        self.assertIn("kopi", rows[0]["content"])
        self.assertTrue(self.db.fts_enabled)

    def test_prefix_query_matches_word_prefix(self):
        self.db.save(self.sid, "user", "deployment pipeline hijau")
        rows = self.db.search("deploy")
        self.assertTrue(rows)
        self.assertIn("deployment", rows[0]["content"])

    def test_punctuation_only_falls_back_to_like(self):
        self.db.save(self.sid, "user", "nilai literal *** di teks")
        rows = self.db.search("***")
        self.assertEqual(len(rows), 1)

    def test_empty_query_returns_newest_rows(self):
        self.db.save(self.sid, "user", "pertama")
        self.db.save(self.sid, "assistant", "kedua")
        rows = self.db.search("", limit=10)
        self.assertEqual(rows[0]["content"], "kedua")

    def test_saved_secret_is_redacted(self):
        self.db.save(self.sid, "tool", "token=abcdefgh12345")
        self.assertNotIn("abcdefgh12345", self.db.history(self.sid)[0]["content"])

    def test_graceful_without_fts5(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = SessionDB(Path(tmp), enable_fts=False)
            sid = db.new_session()
            db.save(sid, "user", "tanpa fts tetap bisa dicari")
            self.assertFalse(db.fts_enabled)
            self.assertTrue(db.search("dicari"))

    def test_tool_events_and_metrics(self):
        self.db.record_tool_event(self.sid, "read_file", "ok", 12, "{}", "isi")
        self.db.record_tool_event(self.sid, "run_terminal", "denied", 3, "{}", "DITOLAK")
        self.db.record_tool_event(self.sid, "rag_search", "error", 40, "{}", "ERROR")
        events = self.db.tool_events(self.sid, limit=10)
        self.assertEqual(len(events), 3)
        metrics = self.db.tool_metrics(self.sid)
        self.assertEqual(metrics["total_calls"], 3)
        self.assertEqual(metrics["by_status"]["ok"], 1)
        self.assertEqual(metrics["max_duration_ms"], 40)
        tools = {row["tool"] for row in metrics["by_tool"]}
        self.assertEqual(tools, {"read_file", "run_terminal", "rag_search"})

    def test_tool_event_preview_redacted(self):
        self.db.record_tool_event(self.sid, "run_terminal", "ok", 1, "api_key=rahasia-banget", "ok")
        event = self.db.tool_events(self.sid)[0]
        self.assertNotIn("rahasia-banget", event["args_preview"])


class WorkspaceTests(unittest.TestCase):
    def test_get_workspace_precedence(self):
        cfg = Config(workspace="/tmp/ws-dari-config")
        self.assertEqual(file_tools.get_workspace({"cfg": cfg}), Path("/tmp/ws-dari-config").resolve())
        with mock.patch.dict("os.environ", {"LACTION_WORKSPACE": "/tmp/ws-env"}):
            self.assertEqual(file_tools.get_workspace(), Path("/tmp/ws-env").resolve())
            # cfg menang atas env
            self.assertEqual(file_tools.get_workspace({"cfg": cfg}), Path("/tmp/ws-dari-config").resolve())

    def test_safe_blocks_traversal_with_context(self):
        with self.assertRaises(ValueError):
            file_tools._safe("../etc/passwd", {"cfg": Config(workspace="/tmp")})

    def test_write_file_blocks_control_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Config(workspace=tmp)
            result = file_tools.write_file("mcp_servers.json", "{}", {"cfg": cfg})
            self.assertIn("DITOLAK", result)
            self.assertFalse((Path(tmp) / "mcp_servers.json").exists())
            ok = file_tools.write_file("data/biasa.txt", "halo", {"cfg": cfg})
            self.assertIn("Berhasil", ok)


class SandboxTests(unittest.TestCase):
    def test_build_command_hardening_flags(self):
        cmd = DockerExecutor("python:3.11-slim").build_command(["python3", "-c", "print(1)"], Path("/tmp"))
        joined = " ".join(cmd)
        for flag in (
            "--network none",
            "--read-only",
            "--cap-drop ALL",
            "--security-opt no-new-privileges",
            "--pids-limit 64",
            "--memory 256m",
            "--cpus 1.0",
            "--user 65534:65534",
        ):
            self.assertIn(flag, joined)
        self.assertIn("/workspace:ro", joined)

    def test_empty_argv_rejected(self):
        with self.assertRaises(ValueError):
            DockerExecutor().build_command([], Path("/tmp"))

    def test_mode_none_is_local(self):
        self.assertEqual(resolve_execution_backend("none")[0], "local")

    def test_docker_mode_fails_closed_without_docker(self):
        with mock.patch.object(DockerExecutor, "has_docker_cli", staticmethod(lambda: False)):
            backend, reason = resolve_execution_backend("docker")
        self.assertEqual(backend, "blocked")
        self.assertIn("DITOLAK", reason)

    def test_auto_mode_degrades_to_local(self):
        with mock.patch.object(DockerExecutor, "is_daemon_ready", staticmethod(lambda timeout=2.0: False)):
            self.assertEqual(resolve_execution_backend("auto")[0], "local")

    def test_run_python_and_terminal_still_deny_without_approval(self):
        reg = get_registry()
        for mode in ("smart", "always"):
            py = reg.call("run_python", {"code": "print(1)"}, context={"approval_mode": mode, "sandbox_mode": "auto"})
            self.assertIn("PERLU APPROVAL", py)
        denied = reg.call("run_python", {"code": "print(1)"}, context={"approval_mode": "never"})
        self.assertIn("DITOLAK", denied)
        term = reg.call("run_terminal", {"command": "echo hi"}, context={"approval_mode": "smart"})
        self.assertIn("PERLU APPROVAL", term)


class TeamTimeoutTests(unittest.TestCase):
    def test_resolve_timeout_clamps(self):
        cfg = Config(team_timeout_seconds=45)
        self.assertEqual(resolve_team_timeout(cfg), 45)
        self.assertEqual(resolve_team_timeout(cfg, 9999), MAX_TEAM_TIMEOUT)
        self.assertEqual(resolve_team_timeout(cfg, 0), MIN_TEAM_TIMEOUT)
        cfg_bad = Config(team_timeout_seconds=45)
        cfg_bad.team_timeout_seconds = "bukan-angka"
        self.assertEqual(resolve_team_timeout(cfg_bad), 45)

    def test_run_team_returns_within_deadline(self):
        from laction_agent import team as team_mod

        def slow_agent(*_args, **_kwargs):
            time.sleep(3)
            return "terlambat"

        cfg = Config(team_timeout_seconds=5)
        started = time.monotonic()
        with mock.patch.object(team_mod, "_gate", threading.BoundedSemaphore(1)), \
                mock.patch("laction_agent.agent.AIAgent", side_effect=slow_agent):
            result = team_mod.run_team(cfg, "tugas", roles=["research"], timeout_seconds=5)
        elapsed = time.monotonic() - started
        self.assertIn("TIMEOUT", result)
        # Deadline 5s: tidak boleh melebar jauh melewati anggaran wall-clock.
        self.assertLess(elapsed, 7.0)
        self.assertIn("batas wall-clock tim", result)


class MCPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.registry = MCPRegistry(self.home)

    def tearDown(self):
        self.tmp.cleanup()

    def test_registry_add_remove_and_persist(self):
        server = self.registry.add_server("demo", sys.executable, ["-m", "laction_agent.mcp.demo_server"])
        self.assertEqual(server["name"], "demo")
        self.assertTrue(self.registry.path.exists())
        reloaded = MCPRegistry(self.home)
        self.assertIsNotNone(reloaded.get("demo"))
        self.assertTrue(reloaded.remove_server("demo"))
        self.assertIsNone(reloaded.get("demo"))
        self.assertFalse(reloaded.remove_server("demo"))

    def test_registry_validation(self):
        with self.assertRaises(ValueError):
            self.registry.add_server("Nama Salah!", sys.executable)
        with self.assertRaises(ValueError):
            self.registry.add_server("ok", "")
        with self.assertRaises(ValueError):
            self.registry.add_server("ok", "python3 -c x")

    def test_registry_ignores_corrupt_file(self):
        self.registry.path.write_text("{bukan json", encoding="utf-8")
        self.assertEqual(self.registry.list_servers(), [])

    def test_stdio_roundtrip(self):
        with MCPStdioClient(sys.executable, ["-m", "laction_agent.mcp.demo_server"], timeout=20) as client:
            info = client.initialize()
            self.assertEqual(info["serverInfo"]["name"], "laction-demo")
            tools = {t["name"]: t for t in client.list_tools()}
            self.assertIn("ping", tools)
            self.assertIn("inputSchema", tools["ping"])
            self.assertEqual(client.call_tool("ping", {"message": "halo"}), "pong: halo")

    def test_unknown_tool_reports_error(self):
        with MCPStdioClient(sys.executable, ["-m", "laction_agent.mcp.demo_server"], timeout=20) as client:
            client.initialize()
            with self.assertRaises(MCPError):
                client.call_tool("tidak_ada", {})

    def test_timeout_raises(self):
        with MCPStdioClient(sys.executable, ["-c", "import time; time.sleep(30)"], timeout=1) as client:
            with self.assertRaises(MCPError):
                client.request("initialize", {})

    def test_client_env_is_stripped(self):
        client = MCPStdioClient("python3", [], {"EXPLICIT": "1"})
        self.assertNotIn("LACTION_API_KEY", client.env)
        self.assertEqual(client.env["EXPLICIT"], "1")

    def test_mcp_tools_denied_by_default(self):
        reg = get_registry()
        self.assertNotIn("mcp_call", READ_ONLY_TOOLS)
        self.registry.add_server("demo", sys.executable, ["-m", "laction_agent.mcp.demo_server"])
        denied = reg.call(
            "mcp_call",
            {"server": "demo", "tool": "ping"},
            context={"approval_mode": "never", "cfg": Config(home=str(self.home))},
        )
        self.assertIn("DITOLAK", denied)
        need = reg.call(
            "mcp_call",
            {"server": "demo", "tool": "ping"},
            context={"approval_mode": "smart", "cfg": Config(home=str(self.home))},
        )
        self.assertIn("PERLU APPROVAL", need)

    def test_mcp_call_rejects_unlisted_server(self):
        reg = get_registry()
        result = reg.call(
            "mcp_call",
            {"server": "liar", "tool": "ping"},
            context={"approval_mode": "smart", "cfg": Config(home=str(self.home)), "approve": lambda _p: True},
        )
        self.assertIn("DITOLAK", result)

    def test_mcp_call_uses_schema_validation(self):
        self.registry.add_server("demo", sys.executable, ["-m", "laction_agent.mcp.demo_server"])
        reg = get_registry()
        result = reg.call(
            "mcp_call",
            {"server": "demo", "tool": "ping", "arguments": {"message": "hai"}},
            context={"approval_mode": "smart", "cfg": Config(home=str(self.home)), "approve": lambda _p: True},
        )
        self.assertEqual(result, "pong: hai")
        unknown = reg.call(
            "mcp_call",
            {"server": "demo", "tool": "tidak_ada"},
            context={"approval_mode": "smart", "cfg": Config(home=str(self.home)), "approve": lambda _p: True},
        )
        self.assertIn("DITOLAK", unknown)


class CliAndSurfaceTests(unittest.TestCase):
    def test_parser_accepts_new_globals(self):
        args = parse_args(["--workspace", "/tmp/ws", "--sandbox-mode", "docker", "status"])
        self.assertEqual(args.workspace, "/tmp/ws")
        self.assertEqual(args.sandbox_mode, "docker")
        self.assertEqual(args.command, "status")

    def test_parser_accepts_new_subcommands(self):
        args = parse_args(["memory", "prune", "--max-entries", "5", "--max-chars", "900", "--target", "user"])
        self.assertEqual(args.command, "memory")
        self.assertEqual(args.action, "prune")
        self.assertEqual(args.max_entries, 5)
        self.assertEqual(args.target, "user")

        traces = parse_args(["traces", "--limit", "3"])
        self.assertEqual(traces.command, "traces")

        mcp_add = parse_args(["mcp", "add", "--name", "demo", "--command", "python3", "--args", "-m", "x"])
        self.assertEqual(mcp_add.command, "mcp")
        self.assertEqual(mcp_add.mcp_command, "add")
        self.assertEqual(mcp_add.mcp_server_command, "python3")
        self.assertEqual(mcp_add.args, ["-m", "x"])

    def test_build_parser_help_works(self):
        parser = build_parser()
        self.assertIn("traces", parser.format_help())

    def test_gateway_html_has_new_buttons_and_no_localhost(self):
        self.assertIn('data-get="/traces"', HTML)
        self.assertIn('data-get="/mcp"', HTML)
        self.assertIn("prune", HTML)
        self.assertNotIn("localhost", HTML)
        self.assertNotIn("127.0.0.1", HTML)


class AgentInstrumentationTests(unittest.TestCase):
    def test_run_records_tool_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Config(provider="mock", home=tmp, workspace=tmp)
            agent = AIAgent(cfg)
            agent.run("list file")
            events = agent.db.tool_events(agent.session_id)
            self.assertTrue(events)
            self.assertTrue(all(ev["status"] in {"ok", "error", "denied", "reflexion_blocked"} for ev in events))
            self.assertTrue(all(ev["duration_ms"] >= 0 for ev in events))
            metrics = agent.db.tool_metrics(agent.session_id)
            self.assertGreaterEqual(metrics["total_calls"], 1)

    def test_denied_tool_recorded_as_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Config(provider="mock", home=tmp, workspace=tmp, approval_mode="never")
            agent = AIAgent(cfg)
            result = agent.registry.call(
                "run_terminal", {"command": "echo hi"}, context=agent._context()
            )
            self.assertIn("DITOLAK", result)
            agent._record_event("run_terminal", agent._event_status(result), 1, {}, result)
            self.assertEqual(agent.db.tool_events(agent.session_id)[0]["status"], "denied")

    def test_event_status_classification(self):
        self.assertEqual(AIAgent._event_status("ok"), "ok")
        self.assertEqual(AIAgent._event_status("DITOLAK: x"), "denied")
        self.assertEqual(AIAgent._event_status("PERLU APPROVAL: x"), "denied")
        self.assertEqual(AIAgent._event_status("REFLEXION GUARD: x"), "reflexion_blocked")
        self.assertEqual(AIAgent._event_status('{"error": "x"}'), "error")
        self.assertEqual(AIAgent._event_status("TIMEOUT: x"), "error")


class GatewayEndpointTests(unittest.TestCase):
    """Uji handler gateway langsung lewat HTTP server sementara di thread."""

    def setUp(self):
        from laction_agent.gateway import run_server

        self.tmp = tempfile.TemporaryDirectory()
        self.home = self.tmp.name
        self.cfg = Config(provider="mock", home=self.home, workspace=self.home, cron_enabled=False)
        self._server = None
        self._thread = None
        self._run_server = run_server

    def tearDown(self):
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self.tmp.cleanup()

    def _start(self):
        from laction_agent.gateway import _LactionHTTPServer, make_handler
        import threading as _t

        agents: dict = {}
        handler = make_handler(
            self.cfg, None, agents, _t.Lock(), _t.Lock(), None
        )
        self._server = _LactionHTTPServer(("127.0.0.1", 0), handler)
        self._thread = _t.Thread(target=self._server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        self._thread.start()
        return self._server.server_address[1]

    def _get(self, port, path):
        import urllib.request

        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))

    def _post(self, port, path, payload):
        import urllib.request

        req = urllib.request.Request(
            f"http://127.0.0.1:{port}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))

    def test_traces_endpoint(self):
        db = SessionDB(Path(self.home))
        sid = db.new_session()
        db.record_tool_event(sid, "read_file", "ok", 7, "{}", "isi")
        port = self._start()
        status, data = self._get(port, f"/traces?session_id={sid}")
        self.assertEqual(status, 200)
        self.assertEqual(data["metrics"]["total_calls"], 1)
        self.assertEqual(data["events"][0]["tool_name"], "read_file")

    def test_mcp_endpoint_lists_servers(self):
        MCPRegistry(Path(self.home)).add_server("demo", "python3", ["-m", "x"])
        port = self._start()
        status, data = self._get(port, "/mcp")
        self.assertEqual(status, 200)
        self.assertEqual(data["servers"][0]["name"], "demo")

    def test_memory_redaction_and_prune(self):
        port = self._start()
        status, data = self._post(port, "/memory", {"note": "api_key=rahasia-gateway-777"})
        self.assertEqual(status, 200)
        self.assertTrue(data["redacted"])
        self.assertNotIn("rahasia-gateway-777", (Path(self.home) / "MEMORY.md").read_text(encoding="utf-8"))

        manager = MemoryManager(Path(self.home))
        for i in range(20):
            manager.append_memory(f"baris {i}")
        status, data = self._post(port, "/memory", {"action": "prune", "max_entries": 3, "max_chars": 800})
        self.assertEqual(status, 200)
        self.assertIn("stats", data)
        self.assertGreater(data["stats"]["removed_entries"], 0)

        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._post(port, "/memory", {"action": "prune", "target": "salah"})
        self.assertEqual(ctx.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
