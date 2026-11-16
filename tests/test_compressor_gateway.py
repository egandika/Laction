import tempfile
import threading
import unittest

from laction_agent import gateway
from laction_agent.config import Config
from laction_agent.context_compressor import compress, estimate_tokens
from laction_agent.providers.base import Message, ToolCall


class TestCompressorAndGateway(unittest.TestCase):
    def test_compress_keeps_last_tool_pair(self):
        messages = [
            Message(role="system", content="S"),
            Message(role="user", content="perintah lama"),
            Message(role="assistant", content="", tool_calls=[ToolCall("read_file", {"path": "a"}, "id-1")]),
            Message(role="tool", content="isi a", tool_call_id="id-1"),
            Message(role="assistant", content="siap"),
            Message(role="user", content="perintah baru"),
            Message(role="assistant", content="", tool_calls=[ToolCall("write_file", {"path": "b"}, "id-2")]),
            Message(role="tool", content="x" * 5000, tool_call_id="id-2"),
        ]
        self.assertGreater(estimate_tokens(messages), 200)

        out = compress(messages, limit=200)

        self.assertEqual(out[0].role, "system")
        self.assertLess(estimate_tokens(out), estimate_tokens(messages))
        self.assertTrue(any("Ringkasan" in m.content for m in out if m.role == "user"))
        # Turn terakhir tidak boleh terpotong: assistant(tool_calls) tetap berpasangan dengan tool.
        self.assertEqual(out[-1].role, "tool")
        self.assertEqual(out[-1].tool_call_id, "id-2")
        self.assertTrue(out[-2].tool_calls)
        self.assertEqual(out[-2].tool_calls[0].id, "id-2")

    def test_compress_noop_for_short_history(self):
        messages = [Message(role="system", content="S"), Message(role="user", content="halo")]
        self.assertIs(compress(messages, limit=8000), messages)

    def test_gateway_html_and_handler(self):
        self.assertIn("<!doctype html>", gateway.HTML.lower())
        self.assertIn("/chat", gateway.HTML)
        self.assertIn("fetch(", gateway.HTML)
        self.assertNotIn("localhost", gateway.HTML)  # semua URL relatif untuk preview proxy

        with tempfile.TemporaryDirectory() as tmp:
            cfg = Config(provider="mock", home=tmp, cron_enabled=False).validate()
            handler = gateway.make_handler(
                cfg, None, {}, threading.Lock(), threading.Lock(), None
            )
            self.assertTrue(hasattr(handler, "do_GET"))
            self.assertTrue(hasattr(handler, "do_POST"))
            self.assertTrue(hasattr(handler, "do_OPTIONS"))
