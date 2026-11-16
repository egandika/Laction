"""Tool web: fetch halaman (tanpa dependency eksternal)."""
from __future__ import annotations

import re
import urllib.request

from .registry import get_registry

reg = get_registry()


@reg.register(
    "web_fetch",
    "Ambil isi halaman web (URL) sebagai teks polos (tag HTML dibuang).",
    {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
)
def web_fetch(url: str, context: dict) -> str:
    if not url.startswith(("http://", "https://")):
        return "URL harus diawali http:// atau https://"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "LactionAgent/0.1"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:6000] or "(halaman kosong)"
    except Exception as e:  # noqa: BLE001
        return f"ERROR fetch {url}: {e}"
