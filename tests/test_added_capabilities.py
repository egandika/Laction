import io
import re
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from laction_agent.config import Config
from laction_agent.providers import Message, MockProvider, OpenAICompatProvider, create_provider
from laction_agent.tools import apk_tools, file_tools, search_tool
from laction_agent.tools.python_tool import _approval_display
from laction_agent.tools.registry import get_registry

REPO_ROOT = Path(__file__).resolve().parents[1]


def _u8_length(value: int) -> bytes:
    if value < 0x80:
        return bytes([value])
    return bytes([0x80 | (value >> 8), value & 0xFF])


def _binary_manifest(package: str = "com.example.binary") -> bytes:
    """Tiny valid-enough binary XML manifest with one package attribute."""
    strings = ["manifest", "package", package]
    payload = bytearray()
    offsets = []
    for text in strings:
        raw = text.encode("utf-8")
        offsets.append(len(payload))
        payload += _u8_length(len(text)) + _u8_length(len(raw)) + raw + b"\0"
    string_header_size = 28
    string_offsets_size = 4 * len(strings)
    strings_start = string_header_size + string_offsets_size
    string_chunk_size = strings_start + len(payload)
    string_pool = struct.pack(
        "<HHI", 0x0001, string_header_size, string_chunk_size
    ) + struct.pack(
        "<IIIII", len(strings), 0, 0x100, strings_start, 0
    ) + b"".join(struct.pack("<I", offset) for offset in offsets) + payload

    attr = struct.pack("<III", 0xFFFFFFFF, 1, 2) + struct.pack("<HBBI", 8, 0, 0x03, 2)
    start_size = 36 + len(attr)
    start_element = (
        struct.pack("<HHI", 0x0102, 16, start_size)
        + struct.pack("<II", 1, 0xFFFFFFFF)
        + struct.pack("<IIHHHHHH", 0xFFFFFFFF, 0, 20, 20, 1, 0, 0, 0)
        + attr
    )
    total = 8 + len(string_pool) + len(start_element)
    return struct.pack("<HHI", 0x0003, 8, total) + string_pool + start_element


class TestPythonRunner(unittest.TestCase):
    def test_requires_explicit_approval_even_in_smart_mode(self):
        out = get_registry().call(
            "run_python", {"code": "print('SHOULD_NOT_RUN')"},
            context={"approval_mode": "smart"},
        )
        self.assertIn("PERLU APPROVAL", out)
        self.assertNotIn("SHOULD_NOT_RUN", out)

    def test_approval_display_escapes_terminal_controls(self):
        shown = _approval_display("print('ok')\n" + chr(0x1B) + "[2J" + chr(0x202E))
        self.assertNotIn(chr(0x1B), shown)
        self.assertIn("u001b", shown)
        self.assertIn("u202e", shown)

    def test_runs_after_approval_without_shell(self):
        seen = []
        out = get_registry().call(
            "run_python", {"code": "print(6 * 7)"},
            context={"approval_mode": "smart", "approve": lambda prompt: seen.append(prompt) or True},
        )
        self.assertIn("[exit=0]", out)
        self.assertIn("42", out)
        self.assertIn("run_python", seen[0])

    def test_never_mode_and_denial_fail_closed(self):
        reg = get_registry()
        blocked = reg.call("run_python", {"code": "print('x')"}, context={"approval_mode": "never", "approve": lambda _: True})
        denied = reg.call("run_python", {"code": "print('x')"}, context={"approval_mode": "smart", "approve": lambda _: False})
        self.assertIn("DITOLAK", blocked)
        self.assertIn("DITOLAK", denied)


class TestLocalRag(unittest.TestCase):
    def test_bm25_returns_source_and_redacts_secret(self):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="laction_rag_") as tmp:
            root = Path(tmp)
            (root / "guide.md").write_text(
                "# Local Retrieval\n\nBM25 ranks relevant local documentation chunks.\n"
                "api_key=super-secret-value-12345\n", encoding="utf-8"
            )
            (root / "ignore.txt").write_text("BM25 must not find this excluded input", encoding="utf-8")
            (root / "data").mkdir()
            (root / "data" / "private.md").write_text("BM25 private data", encoding="utf-8")
            rel = str(root.relative_to(REPO_ROOT))
            out = get_registry().call("rag_search", {"query": "BM25 relevant documentation", "path": rel})
        self.assertIn("guide.md:", out)
        self.assertIn("BM25 ranks", out)
        self.assertNotIn("super-secret-value-12345", out)
        self.assertNotIn("private.md", out)
        self.assertIn("bukan vector/embedding", out)

    def test_rag_blocks_paths_outside_workspace(self):
        out = get_registry().call("rag_search", {"query": "secret", "path": "../"})
        self.assertIn("ditolak", out.lower())


class TestWebSearch(unittest.TestCase):
    def test_parser_extracts_result_and_unwraps_redirect(self):
        html = (
            '<a class="result__a" href="/l/?uddg=https%3A%2F%2Fexample.com%2Fdoc">'
            'Example <b>Documentation</b></a>'
            '<a class="result__snippet">A useful source snippet.</a>'
        )
        parser = search_tool._DuckDuckGoParser()
        parser.feed(html)
        parser.close()
        self.assertEqual(len(parser.results), 1)
        self.assertEqual(parser.results[0]["url"], "https://example.com/doc")
        self.assertEqual(parser.results[0]["title"], "Example Documentation")
        self.assertEqual(parser.results[0]["snippet"], "A useful source snippet.")

    def test_secret_queries_are_not_sent_to_search_provider(self):
        with patch("laction_agent.tools.search_tool.urllib.request.urlopen") as opener:
            out = get_registry().call("web_search", {"query": "api_key=private-secret-value-123"})
        self.assertIn("DITOLAK", out)
        opener.assert_not_called()

    def test_search_uses_parser_and_handles_challenge_page(self):
        good = b'<a class="result__a" href="https://example.com">Example</a><a class="result__snippet">Snippet</a>'
        with patch("laction_agent.tools.search_tool.urllib.request.urlopen", return_value=io.BytesIO(good)):
            out = get_registry().call("web_search", {"query": "public docs", "max_results": 3})
        self.assertIn("https://example.com", out)
        self.assertIn("Snippet", out)
        with patch("laction_agent.tools.search_tool.urllib.request.urlopen", return_value=io.BytesIO(b"captcha anomaly")):
            challenged = get_registry().call("web_search", {"query": "public docs"})
        self.assertIn("rate-limit/challenge", challenged)


class TestGeminiProvider(unittest.TestCase):
    def test_gemini_alias_uses_official_openai_compatible_base(self):
        cfg = Config(provider="gemini", model="gemini-test", api_key="test-key").validate()
        provider = create_provider(cfg)
        self.assertIsInstance(provider, OpenAICompatProvider)
        self.assertEqual(provider.api_base, "https://generativelanguage.googleapis.com/v1beta/openai")
        self.assertFalse(cfg.warnings())

    def test_gemini_requires_key_warning(self):
        cfg = Config(provider="gemini", model="gemini-test").validate()
        self.assertTrue(any("API_KEY" in warning for warning in cfg.warnings()))


class TestMockProviderRouting(unittest.TestCase):
    def test_mock_dispatches_new_capabilities_without_network(self):
        examples = {
            "cari web: Python 3.13 docs": ("web_search", "query"),
            "RAG search: local README": ("rag_search", "query"),
            "analisis APK app.apk": ("apk_analyze", "path"),
            "ekstrak apk app.apk member classes.dex ke out/classes.dex": ("apk_extract", "member"),
            "Python: print(2 + 2)": ("run_python", "code"),
        }
        provider = MockProvider()
        for prompt, (tool_name, arg_name) in examples.items():
            with self.subTest(prompt=prompt):
                response = provider.chat([Message("user", prompt)], [])
                self.assertEqual(response.tool_calls[0].name, tool_name)
                self.assertIn(arg_name, response.tool_calls[0].arguments)


class TestApkTools(unittest.TestCase):
    def _make_apk(self, root: Path, binary_manifest: bool = False) -> Path:
        apk = root / "sample.apk"
        manifest = _binary_manifest() if binary_manifest else b'''<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="com.example.audit" android:versionName="1.2" android:versionCode="7">
  <uses-sdk android:minSdkVersion="23" android:targetSdkVersion="34"/>
  <uses-permission android:name="android.permission.CAMERA"/>
  <application android:debuggable="true" android:allowBackup="true" android:usesCleartextTraffic="true">
    <activity android:name=".MainActivity" android:exported="true"/>
  </application>
</manifest>'''
        with zipfile.ZipFile(apk, "w") as archive:
            archive.writestr("AndroidManifest.xml", manifest)
            archive.writestr("classes.dex", b"dex\n035\0 AKIA1234567890ABCDEF https://api.example.test/v1\0")
            archive.writestr("assets/config.txt", b"password=very-long-secret-value-123\n")
        return apk

    def test_static_report_reads_manifest_and_never_prints_secrets(self):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="laction_apk_") as tmp:
            root = Path(tmp)
            self._make_apk(root)
            rel = str(root.relative_to(REPO_ROOT) / "sample.apk")
            out = get_registry().call("apk_analyze", {"path": rel})
        self.assertIn("APK STATIC ANALYSIS", out)
        self.assertIn("Package: com.example.audit", out)
        self.assertIn("[HIGH] android:debuggable=true", out)
        self.assertIn("android.permission.CAMERA [sensitive]", out)
        self.assertIn(".MainActivity", out)
        self.assertIn("credential-like", out.lower())
        self.assertNotIn("AKIA1234567890ABCDEF", out)
        self.assertNotIn("very-long-secret-value-123", out)
        self.assertIn("api.example.test", out)

    def test_binary_axml_manifest_is_parsed(self):
        parsed = apk_tools._manifest_summary(apk_tools._parse_manifest(_binary_manifest()))
        self.assertEqual(parsed["package"], "com.example.binary")

    def test_apk_extract_is_single_entry_and_workspace_bounded(self):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="laction_apk_") as tmp:
            root = Path(tmp)
            self._make_apk(root)
            rel = str(root.relative_to(REPO_ROOT))
            out = get_registry().call(
                "apk_extract",
                {"path": f"{rel}/sample.apk", "member": "classes.dex", "output_path": f"{rel}/out/classes.dex"},
            )
            self.assertIn("berhasil mengekstrak", out.lower())
            self.assertEqual((root / "out" / "classes.dex").read_bytes().startswith(b"dex"), True)
            blocked = get_registry().call(
                "apk_extract",
                {"path": f"{rel}/sample.apk", "member": "classes.dex", "output_path": "../escaped.dex"},
            )
            self.assertIn("ditolak", blocked.lower())
            self.assertFalse((REPO_ROOT.parent / "escaped.dex").exists())


class TestBundledSkillFormat(unittest.TestCase):
    def test_all_bundled_skills_have_spec_shaped_frontmatter(self):
        pattern = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
        root = REPO_ROOT / "laction_agent" / "skills" / "bundled"
        skills = sorted(path for path in root.iterdir() if path.is_dir())
        self.assertGreaterEqual(len(skills), 13)
        for folder in skills:
            with self.subTest(skill=folder.name):
                text = (folder / "SKILL.md").read_text(encoding="utf-8")
                self.assertLessEqual(len(folder.name), 64)
                self.assertRegex(folder.name, pattern)
                self.assertTrue(text.startswith("---\n"))
                header = text.split("\n---\n", 1)[0]
                name_match = re.search(r"^name:\s*(.+)$", header, re.MULTILINE)
                desc_match = re.search(r"^description:\s*(.+)$", header, re.MULTILINE)
                self.assertIsNotNone(name_match)
                self.assertEqual(name_match.group(1).strip(), folder.name)
                self.assertIsNotNone(desc_match)
                self.assertGreater(len(desc_match.group(1).strip()), 0)
                self.assertLessEqual(len(desc_match.group(1).strip()), 1024)
                self.assertLessEqual(len(text.splitlines()), 500)


if __name__ == "__main__":
    unittest.main()
