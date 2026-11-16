import json
import tempfile
import unittest
from pathlib import Path

from laction_agent.cron.scheduler import CronScheduler
from laction_agent.tools import file_tools
from laction_agent.tools.registry import get_registry

REPO_ROOT = Path(__file__).resolve().parents[1]


class TestTools(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Pastikan guard workspace menunjuk ke repo, apa pun cwd pytest.
        file_tools.WORKSPACE = REPO_ROOT.resolve()

    def test_registry_has_core_tools(self):
        names = set(get_registry().names())
        expected = {
            "read_file", "write_file", "list_files", "search_files", "run_terminal",
            "web_fetch", "memory_save", "memory_read", "memory_search", "user_save",
            "list_skills", "view_skill", "create_skill", "delegate_task",
            "cron_add", "cron_list", "cron_remove", "get_time", "list_tools", "agent_info",
        }
        self.assertTrue(expected.issubset(names), f"Missing: {expected - names}")
        schemas = get_registry().schemas()
        self.assertTrue(all("parameters" in s and "description" in s for s in schemas))

    def test_file_roundtrip_and_path_guard(self):
        reg = get_registry()
        with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="laction_test_") as tmp:
            rel = Path(tmp).relative_to(REPO_ROOT) / "catatan.txt"
            written = reg.call("write_file", {"path": str(rel), "content": "halo"}, context={})
            self.assertIn("Berhasil", written)
            self.assertEqual((REPO_ROOT / rel).read_text(encoding="utf-8"), "halo")
            self.assertEqual(reg.call("read_file", {"path": str(rel)}, context={}), "halo")
            listing = reg.call("list_files", {"path": str(rel.parent)}, context={})
            self.assertIn("catatan.txt", listing)

        with self.assertRaises(ValueError):
            file_tools._safe("../etc/passwd")
        with self.assertRaises(ValueError):
            file_tools._safe("/etc/passwd")

    def test_terminal_approval_modes(self):
        reg = get_registry()
        blocked = reg.call(
            "run_terminal", {"command": "echo aman"},
            context={"approval_mode": "always", "approve": None},
        )
        self.assertIn("PERLU APPROVAL", blocked)

        allowed = reg.call(
            "run_terminal", {"command": "echo aman"},
            context={"approval_mode": "always", "approve": lambda _c: True},
        )
        self.assertIn("aman", allowed)
        self.assertIn("exit=0", allowed)

        denied = reg.call(
            "run_terminal", {"command": "rm -rf /tmp/x"},
            context={"approval_mode": "never"},
        )
        self.assertIn("DITOLAK", denied)

    def test_cron_tools_and_unknown_tool(self):
        reg = get_registry()
        with tempfile.TemporaryDirectory() as tmp:
            sched = CronScheduler(Path(tmp))
            added = reg.call(
                "cron_add",
                {"name": "harian", "task": "list file", "interval_seconds": 60},
                context={"cron": sched},
            )
            self.assertIn("ditambahkan", added)
            listed = reg.call("cron_list", {}, context={"cron": sched})
            self.assertIn("harian", listed)
            removed = reg.call("cron_remove", {"name": "harian"}, context={"cron": sched})
            self.assertIn("dihapus", removed)

        err = json.loads(reg.call("tidak_ada", {}, context={}))
        self.assertIn("error", err)
        self.assertIn("available", err)
