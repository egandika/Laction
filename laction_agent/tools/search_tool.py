"""Best-effort public DuckDuckGo HTML search (no API key or extra package)."""
from __future__ import annotations

import re
import urllib.error
import urllib.request
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

from ..utils import redact
from .registry import get_registry

_SEARCH_URL = "https://html.duckduckgo.com/html/"
_MAX_HTML_BYTES = 1_000_000
reg = get_registry()


class _DuckDuckGoParser(HTMLParser):
    """Extract the result anchors/snippets without depending on an HTML package."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.results: list[dict[str, str]] = []
        self.current: dict[str, str] | None = None
        self._in_title = False
        self._in_snippet = False
        self._title: list[str] = []
        self._snippet: list[str] = []

    def _finish(self):
        if self.current:
            self.current["title"] = _clean(" ".join(self._title))
            self.current["snippet"] = _clean(" ".join(self._snippet))
            if self.current.get("title") and self.current.get("url"):
                self.results.append(self.current)
        self.current = None
        self._title, self._snippet = [], []
        self._in_title = self._in_snippet = False

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        attr = dict(attrs)
        classes = set((attr.get("class") or "").split())
        if classes.intersection({"result__a", "result-link"}):
            if self.current:
                self._finish()
            self.current = {"url": _unwrap_url(attr.get("href", "")), "title": "", "snippet": ""}
            self._in_title = True
        elif self.current and classes.intersection({"result__snippet", "result-snippet"}):
            self._in_snippet = True

    def handle_data(self, data):
        if self._in_title:
            self._title.append(data)
        elif self._in_snippet:
            self._snippet.append(data)

    def handle_endtag(self, tag):
        if tag.lower() != "a":
            return
        if self._in_title:
            self._in_title = False
        elif self._in_snippet:
            self._in_snippet = False
            self._finish()

    def close(self):
        super().close()
        self._finish()


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _unwrap_url(href: str) -> str:
    if not href:
        return ""
    parsed = urlparse(href)
    if not parsed.scheme and not parsed.hostname:
        href = urljoin(_SEARCH_URL, href)
        parsed = urlparse(href)
    host = (parsed.hostname or "").lower()
    if (host == "duckduckgo.com" or host.endswith(".duckduckgo.com")) and parsed.path.startswith("/l/"):
        href = parse_qs(parsed.query).get("uddg", [""])[0]
        parsed = urlparse(href)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        return ""
    return href


@reg.register(
    "web_search",
    "Cari web publik via halaman HTML DuckDuckGo (best-effort; bukan API resmi, dapat rate-limit). Query dikirim ke DuckDuckGo.",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Kueri pencarian web"},
            "max_results": {"type": "integer", "description": "Jumlah hasil 1-8 (default 5)", "minimum": 1, "maximum": 8},
        },
        "required": ["query"],
    },
)
def web_search(query: str, max_results: int = 5, context: dict | None = None) -> str:
    query = (query or "").strip()
    if len(query) < 2:
        return "Query minimal 2 karakter."
    if len(query) > 300:
        return "Query dibatasi 300 karakter."
    if redact(query) != query:
        return "DITOLAK: query tampak berisi credential/secret; hapus secret sebelum mencari. Query tidak dikirim."
    limit = min(max(int(max_results), 1), 8)
    url = _SEARCH_URL + "?" + urlencode({"q": query})
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; LactionAgent/0.1; +https://github.com/egandika/Laction)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            html = response.read(_MAX_HTML_BYTES + 1)
        if len(html) > _MAX_HTML_BYTES:
            return "ERROR: halaman hasil pencarian terlalu besar; pencarian dihentikan."
        parser = _DuckDuckGoParser()
        parser.feed(html.decode("utf-8", errors="replace"))
        parser.close()
        results = parser.results[:limit]
        if not results:
            return (
                "DuckDuckGo tidak mengembalikan hasil yang dapat dibaca. Endpoint HTML ini tidak resmi "
                "dan mungkin sedang rate-limit/challenge; coba lagi nanti atau gunakan web_fetch pada URL yang diketahui."
            )
        lines = [f"Hasil DuckDuckGo untuk: {query} (tautan publik; verifikasi halaman sebelum menyimpulkan)"]
        for i, result in enumerate(results, 1):
            lines.append(f"\n[{i}] {redact(result['title'])}\n{redact(result['url'])}")
            if result["snippet"]:
                lines.append(redact(result["snippet"]))
        return "\n".join(lines)
    except urllib.error.HTTPError as exc:
        if exc.code in (202, 403, 429):
            return f"DuckDuckGo membatasi permintaan (HTTP {exc.code}); kurangi frekuensi lalu coba lagi."
        return f"ERROR DuckDuckGo HTTP {exc.code}."
    except Exception as exc:  # noqa: BLE001 — network/parser errors are tool observations
        return f"ERROR pencarian DuckDuckGo: {type(exc).__name__}: {exc}"
