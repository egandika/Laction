import unittest

from laction_agent.cli import parse_args


class TestCLIParser(unittest.TestCase):
    def test_multiword_message_is_not_a_subcommand(self):
        args = parse_args(["list", "file"])
        self.assertIsNone(args.command)
        self.assertEqual(args.message, ["list", "file"])

    def test_global_option_before_message(self):
        args = parse_args(["--home", "/tmp/profil", "ingat:", "saya", "suka", "kopi"])
        self.assertIsNone(args.command)
        self.assertEqual(args.home, "/tmp/profil")
        self.assertEqual(args.message, ["ingat:", "saya", "suka", "kopi"])

    def test_run_subcommand_keeps_all_words(self):
        args = parse_args(["run", "jalankan", "echo", "halo"])
        self.assertEqual(args.command, "run")
        self.assertEqual(args.text, ["jalankan", "echo", "halo"])

    def test_status_subcommand_with_flag(self):
        args = parse_args(["--home", "/tmp/profil", "status", "--json"])
        self.assertEqual(args.command, "status")
        self.assertTrue(args.json)
        self.assertEqual(args.home, "/tmp/profil")

    def test_memory_subcommand_with_note(self):
        args = parse_args(["memory", "add", "catatan panjang"])
        self.assertEqual(args.command, "memory")
        self.assertEqual(args.action, "add")
        self.assertEqual(args.note, ["catatan panjang"])

    def test_empty_args_goes_to_interactive(self):
        args = parse_args([])
        self.assertIsNone(args.command)
        self.assertEqual(args.message, [])

    def test_global_option_after_subcommand(self):
        args = parse_args(["status", "--home", "/tmp/profil", "--json"])
        self.assertEqual(args.command, "status")
        self.assertEqual(args.home, "/tmp/profil")
        self.assertTrue(args.json)

    def test_global_option_after_nested_cron_subcommand(self):
        args = parse_args([
            "cron", "add", "--home", "/tmp/profil",
            "--name", "harian", "--task", "list file", "--interval", "60",
        ])
        self.assertEqual(args.command, "cron")
        self.assertEqual(args.cron_command, "add")
        self.assertEqual(args.home, "/tmp/profil")
        self.assertEqual(args.name, "harian")
        self.assertEqual(args.task, "list file")

    def test_global_option_equals_syntax(self):
        args = parse_args(["tools", "--home=/tmp/profil"])
        self.assertEqual(args.command, "tools")
        self.assertEqual(args.home, "/tmp/profil")

    def test_help_stays_with_subcommand(self):
        raw = ["gateway", "--help"]
        with self.assertRaises(SystemExit) as ctx:
            parse_args(raw)
        self.assertEqual(ctx.exception.code, 0)
