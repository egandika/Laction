import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from laction_agent.agent import AIAgent
from laction_agent.cli import main
from laction_agent.config import Config
from laction_agent.tools import file_tools

REPO_ROOT = Path(__file__).resolve().parents[1]


def make_cfg(home: str, **kw) -> Config:
    return Config(provider="mock", home=home, max_iterations=5, **kw).validate()


class TestAgent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        file_tools.WORKSPACE = REPO_ROOT.resolve()

    def test_mock_tool_loop_terminates(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = AIAgent(make_cfg(tmp))
            reply = agent.run("list file")
        self.assertIn("Selesai", reply)
        self.assertIn("pyproject.toml", reply)
        self.assertNotIn("batas iterasi", reply)

    def test_memory_save_read_and_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = AIAgent(make_cfg(tmp), session_id="s-memory-test")
            saved = agent.run("ingat: saya suka kopi")
            self.assertIn("Tersimpan", saved)
            self.assertIn("saya suka kopi", (Path(tmp) / "MEMORY.md").read_text(encoding="utf-8"))

            recalled = agent.run("apa yang kamu ingat?")
            self.assertIn("saya suka kopi", recalled)

            searched = agent.run("cari ingatan kopi")
            self.assertIn("saya suka kopi", searched)

    def test_skill_self_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = AIAgent(make_cfg(tmp))
            created = agent.run("buat skill kopi: 1. seduh 2. sajikan")
            self.assertIn("dibuat", created)
            self.assertTrue((Path(tmp) / "skills" / "kopi" / "SKILL.md").exists())

            listed = agent.run("list skill")
            self.assertIn("kopi", listed)
            self.assertIn("repo-onboarding", listed)  # skill bawaan ikut terbaca

    def test_delegate_uses_isolated_subagent(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = AIAgent(make_cfg(tmp))
            reply = agent.run("delegasikan: list tool")
        self.assertIn("Selesai", reply)
        self.assertIn("list_tools", reply)

    def test_cli_one_shot(self):
        with tempfile.TemporaryDirectory() as tmp:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = main(["--home", tmp, "list", "file"])
            out = buf.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("Selesai", out)
