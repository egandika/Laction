import os
import tempfile
import unittest
from pathlib import Path

from laction_agent.config import Config, _load_yaml_minimal


class TestConfig(unittest.TestCase):
    def setUp(self):
        self._saved_env = {k: v for k, v in os.environ.items() if k.startswith("LACTION_")}
        self._clear_env()

    def tearDown(self):
        self._clear_env()
        os.environ.update(self._saved_env)

    @staticmethod
    def _clear_env():
        for key in [k for k in os.environ if k.startswith("LACTION_")]:
            del os.environ[key]

    def test_defaults_without_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = os.getcwd()
            os.chdir(tmp)
            try:
                cfg = Config.load()
            finally:
                os.chdir(old)
        self.assertEqual(cfg.provider, "mock")
        self.assertEqual(cfg.home, "./data")
        self.assertEqual(cfg.max_iterations, 10)
        self.assertEqual(cfg.approval_mode, "smart")
        self.assertTrue(cfg.cron_enabled)

    def test_precedence_config_dotenv_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = os.getcwd()
            os.chdir(tmp)
            try:
                Path("config.yaml").write_text(
                    "provider: openai\nmodel: dari-yaml\nmax_iterations: 3\n"
                    "approval_mode: smart   # komentar inline\ncron_enabled: false\n",
                    encoding="utf-8",
                )
                Path(".env").write_text(
                    "LACTION_PROVIDER=mock\nLACTION_MODEL=dari-dotenv\nLACTION_MAX_ITERATIONS=7\n",
                    encoding="utf-8",
                )
                os.environ["LACTION_MAX_ITERATIONS"] = "9"
                cfg = Config.load()
            finally:
                os.chdir(old)
        self.assertEqual(cfg.provider, "mock")          # .env mengalahkan config.yaml
        self.assertEqual(cfg.model, "dari-dotenv")
        self.assertEqual(cfg.max_iterations, 9)         # env proses paling tinggi
        self.assertEqual(cfg.approval_mode, "smart")    # komentar inline dibuang
        self.assertFalse(cfg.cron_enabled)              # bool coercion

    def test_yaml_minimal_parser(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "c.yaml"
            p.write_text('provider: "ollama" # catatan\nhome: ./profil\n', encoding="utf-8")
            data = _load_yaml_minimal(p)
        self.assertEqual(data["provider"], "ollama")
        self.assertEqual(data["home"], "./profil")

    def test_validation_and_redaction(self):
        with self.assertRaises(ValueError):
            Config(provider="aneh").validate()
        with self.assertRaises(ValueError):
            Config(approval_mode="ganas").validate()
        with self.assertRaises(ValueError):
            Config(max_iterations=0).validate()

        cfg = Config(api_key="sk-rahasia123456").validate()
        self.assertTrue(cfg.as_dict()["api_key"].startswith("***"))
        self.assertNotIn("rahasia123456", cfg.as_dict()["api_key"])
        self.assertTrue(any("API_KEY" in w for w in Config(provider="openai").warnings()))
