"""
Tool web: fetch halaman (tanpa dependency eksternal) + SSRF guard.

Review menemukan `web_fetch` bisa diarahkan LLM ke alamat internal
(cloud metadata 169.254.169.254, localhost, 10.x, dll). Sekarang target
privat/link-local ditolak secara default. Opt-out eksplisit:
`LACTION_ALLOW_PRIVATE_WEB=1` (mis. untuk dev lokal yang memang disengaja).
"""
from __future__ import annotations

import ipaddress
import os
import re
import socket
import urllib.request
from urllib.parse import urlparse

from .registry import get_registry

reg = get_registry()

_PRIVATE_HOST_SUFFIXES = (".localhost", ".local", ".internal", ".localdomain")


def _private_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(
        ip.is_private or ip.is_loopback or ip.is_link_local
        or ip.is_reserved or ip.is_multicast or ip.is_unspecified
    )


def _is_blocked_url(url: str, allow_private: bool | None = None) -> bool:
    """True bila target harus ditolak. Tidak melakukan request jaringan.

    `allow_private=None` mengikuti env LACTION_ALLOW_PRIVATE_WEB; nilai
    eksplisit dipakai `doctor` agar health check tidak bergantung pada env.
    """
    if allow_private is None:
        allow_private = os.environ.get("LACTION_ALLOW_PRIVATE_WEB", "").strip().lower() in (
            "1", "true", "yes", "on",
        )
    if allow_private:
        return False
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return True
    host = (parsed.hostname or "").lower().strip("[]")
    if not host:
        return True
    if host == "localhost" or host.endswith(_PRIVATE_HOST_SUFFIXES):
        return True
    try:
        return _private_ip(ipaddress.ip_address(host))
    except ValueError:
        pass
    # Hostname: cek hasil DNS agar `evil.test -> 127.0.0.1` tidak lolos.
    try:
        resolved = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except OSError:
        return False  # biarkan urlopen yang melaporkan kegagalan DNS
    for addr in resolved:
        try:
            if _private_ip(ipaddress.ip_address(addr)):
                return True
        except ValueError:
            continue
    return False


@reg.register(
    "web_fetch",
    "Ambil isi halaman web publik (URL) sebagai teks polos. Alamat privat ditolak.",
    {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
)
def web_fetch(url: str, context: dict) -> str:
    if not url.startswith(("http://", "https://")):
        return "URL harus diawali http:// atau https://"
    if _is_blocked_url(url):
        return (
            "DITOLAK: akses ke alamat privat/link-local diblokir (SSRF guard). "
            "Set LACTION_ALLOW_PRIVATE_WEB=1 bila memang disengaja."
        )
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
