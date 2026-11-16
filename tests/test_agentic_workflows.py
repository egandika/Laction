import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from laction_agent.agent import AIAgent
from laction_agent.config import Config
from laction_agent.policies import READ_ONLY_TOOLS
from laction_agent.providers.base import ProviderResponse, ToolCall
from laction_agent.skills.manager import SkillManager
from laction_agent.tools.registry import get_registry
from laction_agent.tools.simulation_tool import evolve_plan
from laction_agent.team import run_team
from laction_agent import cli


class TestScopedAgents(unittest.TestCase):
    def test_scope_is_enforced_even_for_unadvertised_tool_calls(self):
        class RogueProvider:
            def __init__(self):
                self.count = 0
            def chat(self, messages, tools):
                self.asserted_tools = [tool["name"] for tool in tools]
                self.count += 1
                if self.count == 1:
                    return ProviderResponse(tool_calls=[ToolCall("write_file", {"path": "must-not-exist.txt", "content": "bad"}, "1")])
                return ProviderResponse(content=messages[-1].content)
        with tempfile.TemporaryDirectory() as home:
            agent = AIAgent(Config(home=home), allowed_tools=READ_ONLY_TOOLS)
            provider = RogueProvider()
            agent.provider = provider
            self.assertIn("DITOLAK", agent.run("test"))
            self.assertNotIn("write_file", provider.asserted_tools)
            self.assertFalse(Path("must-not-exist.txt").exists())

    def test_scheduled_runs_have_read_only_scope(self):
        with tempfile.TemporaryDirectory() as home, patch("laction_agent.cli.AIAgent") as agent:
            scheduler = cli._cron_scheduler(Config(home=home))
            scheduler.on_run("test")
            self.assertEqual(agent.call_args.kwargs["allowed_tools"], READ_ONLY_TOOLS)

    def test_scope_blocks_delegate_and_shell(self):
        reg = get_registry()
        for name in ("run_terminal", "run_python", "write_file", "cron_add", "consult_team", "web_search"):
            self.assertIn("DITOLAK", reg.call(name, {}, {"allowed_tools": READ_ONLY_TOOLS}))

    def test_team_runs_parallel_and_review_receives_findings(self):
        barrier = threading.Barrier(2, timeout=5)
        calls = []
        lock = threading.Lock()
        class FakeAgent:
            def __init__(self, cfg, **kwargs):
                self.role = kwargs["role"]
                self.allowed = kwargs["allowed_tools"]
                self.iterations = cfg.max_iterations
            def run(self, task):
                with lock:
                    calls.append((self.role, task, self.allowed, self.iterations))
                if "Evaluator" not in self.role:
                    barrier.wait()
                    return "bukti " + self.role[:15]
                return "klaim perlu verifikasi"
        with tempfile.TemporaryDirectory() as home, patch("laction_agent.agent.AIAgent", FakeAgent):
            result = run_team(Config(home=home, max_iterations=20), "audit", ["apk", "research"])
        self.assertEqual(len(calls), 3)
        self.assertTrue(all(c[2] == READ_ONLY_TOOLS and c[3] == 4 for c in calls))
        self.assertIn("[apk]", calls[-1][1])
        self.assertIn("[research]", calls[-1][1])
        self.assertIn("klaim perlu verifikasi", result)

    def test_team_rejects_unbounded_or_unknown_roles(self):
        cfg = Config()
        for roles in ([], ["apk"] * 2, ["apk", "report", "research"], ["shell"], [["apk"]]):
            self.assertIn("ERROR", run_team(cfg, "hello", roles))

    def test_mock_team_reviewer_is_honest(self):
        with tempfile.TemporaryDirectory() as home:
            result = AIAgent(Config(home=home)).run("tim: list file")
            self.assertIn("Mode mock tidak dapat memverifikasi", result)
            self.assertNotIn("tool run_terminal", result)

    def test_health_read_only(self):
        result = get_registry().call("device_health", {}, {"allowed_tools": READ_ONLY_TOOLS})
        self.assertIn("Storage", result)
        self.assertIn("RAM", result)


class TestSkillApproval(unittest.TestCase):
    def test_approval_required_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as home:
            mgr = SkillManager(Path(home))
            reg = get_registry()
            args = {"name": "new-skill", "content": "langkah aman"}
            self.assertIn("APPROVAL", reg.call("create_skill", args, {"skills": mgr}))
            self.assertIsNone(mgr.view_skill("new-skill"))
            prompts = []
            ctx = {"skills": mgr, "approve": lambda prompt: prompts.append(prompt) or True}
            self.assertIn("dibuat", reg.call("create_skill", args, ctx))
            self.assertIn("langkah aman", prompts[0])
            self.assertIn("DITOLAK", reg.call("create_skill", {**args, "content": "overwrite"}, ctx))
            self.assertNotIn("overwrite", mgr.view_skill("new-skill"))
            self.assertIn("DITOLAK", reg.call("create_skill", {**args, "name": "planning"}, ctx))

    def test_denied_and_exception_fail_closed(self):
        with tempfile.TemporaryDirectory() as home:
            mgr = SkillManager(Path(home))
            args = {"name": "baru", "content": "test"}
            reg = get_registry()
            self.assertIn("DITOLAK", reg.call("create_skill", args, {"skills": mgr, "approve": lambda _: False}))
            def broken(_):
                raise ValueError("oops")
            self.assertIn("ERROR", reg.call("create_skill", args, {"skills": mgr, "approve": broken}))
            self.assertIsNone(mgr.view_skill("baru"))


class TestEvolution(unittest.TestCase):
    options = [
        {"name": "A", "cost": 2, "benefits": [4, 3]},
        {"name": "B", "cost": 3, "benefits": [3, 5]},
        {"name": "C", "cost": 6, "benefits": [20, 20]},
    ]

    def test_reproducible_and_feasible_with_exact_scores(self):
        kwargs = dict(options=self.options, budget=5, population=40, generations=6, seed=42)
        a = evolve_plan(**kwargs)
        self.assertEqual(a, evolve_plan(**kwargs))
        result = json.loads(a)
        selected = [o for o in self.options if o["name"] in result["selected"]]
        self.assertLessEqual(sum(o["cost"] for o in selected), 5)
        totals = [sum(o["benefits"][i] for o in selected) for i in range(2)]
        self.assertEqual(result["scenario_totals"], totals)
        self.assertEqual(result["worst_case_score"], min(totals))
        self.assertEqual(result["best_by_generation"][-1], result["worst_case_score"])
        self.assertEqual(result["best_by_generation"], sorted(result["best_by_generation"]))
        self.assertIn("bukan sandbox", result["limitation"])

    def test_rejects_invalid_inputs(self):
        bad = [float("nan"), float("inf"), -1, 10**1000, True]
        for value in bad:
            self.assertIn("ERROR", evolve_plan(self.options, value))
        self.assertIn("ERROR", evolve_plan(self.options, 5, population=1000))
        self.assertIn("ERROR", evolve_plan(self.options, 5, generations=11))
        self.assertIn("ERROR", evolve_plan([{"name": "x", "cost": 1, "benefits": [1]}, {"name": "y", "cost": 1, "benefits": [1, 2]}], 5))

class TestVirtualWorld(unittest.TestCase):
    def test_virtual_changes_never_touch_real_files(self):
        from laction_agent.tools.simulation_tool import simulate_files
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp) / "real.txt"
            real.write_text("real")
            result = json.loads(simulate_files({"real.txt": "copy"}, [
                {"op": "delete", "path": "real.txt"},
                {"op": "write", "path": "new.txt", "content": "virtual"},
                {"op": "read", "path": "new.txt"},
            ]))
            self.assertEqual(real.read_text(), "real")
            self.assertFalse((Path(tmp) / "new.txt").exists())
            self.assertEqual(result["final_paths"], ["new.txt"])
            self.assertEqual(result["events"][-1]["content"], "virtual")

    def test_virtual_rejects_shell_traversal_and_limits(self):
        from laction_agent.tools.simulation_tool import simulate_files
        self.assertIn("ERROR", simulate_files({}, [{"op": "shell", "path": "rm -rf /"}]))
        self.assertIn("ERROR", simulate_files({}, [{"op": "write", "path": "../secret", "content": "x"}]))
        self.assertIn("ERROR", simulate_files({}, [{"op": "list"}] * 51))
        self.assertIn("ERROR", simulate_files({"a": "x" * 65537}, []))

    def test_mock_routes_health_and_evolution(self):
        with tempfile.TemporaryDirectory() as home:
            agent = AIAgent(Config(home=home))
            self.assertIn("Storage", agent.run("cek kesehatan"))
            result = agent.run('evolusi: {"options":[{"name":"a","cost":1,"benefits":[2]}],"budget":1}')
            self.assertIn("worst_case_score", result)

class TestAdditionalGuards(unittest.TestCase):
    def test_shell_requires_approval_even_for_smart_and_never(self):
        reg = get_registry()
        args = {"command": "echo aman"}
        with patch("laction_agent.tools.terminal_tool.subprocess.run") as run:
            self.assertIn("APPROVAL", reg.call("run_terminal", args, {"approval_mode": "smart"}))
            self.assertIn("DITOLAK", reg.call("run_terminal", args, {"approval_mode": "never"}))
            run.assert_not_called()

    def test_scheduler_cap_does_not_start_fourth_worker(self):
        from laction_agent.cron.scheduler import CronScheduler
        with tempfile.TemporaryDirectory() as home:
            started = []
            scheduler = CronScheduler(Path(home), on_run=started.append)
            scheduler._running.update({"one", "two", "three"})
            scheduler._trigger({"name": "four", "task": "should not run"})
            self.assertEqual(started, [])
            self.assertNotIn("four", scheduler._running)


if __name__ == "__main__":
    unittest.main()
