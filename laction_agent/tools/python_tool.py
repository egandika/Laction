"""Explicitly approved Python runner for local experiments and debugging."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from ..utils import truncate
from .registry import get_registry

MAX_CODE_CHARS = 20_000
MAX_TIMEOUT_SECONDS = 30


def _approval_display(code: str) -> str:
    """Escape terminal control/bidi chars so approval text cannot spoof the CLI."""
    return "".join(
        char if char.isprintable() or char in "\n\t" else f"\\u{ord(char):04x}"
        for char in code
    )


reg = get_registry()


@reg.register(
    "run_python",
    "Jalankan potongan Python lokal untuk eksperimen/debug. Arbitrary code, BUKAN sandbox; selalu perlu persetujuan eksplisit.",
    {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Kode Python yang akan dijalankan"},
            "timeout_seconds": {
                "type": "integer",
                "description": "Batas waktu 1-30 detik (default 10)",
                "minimum": 1,
                "maximum": 30,
            },
        },
        "required": ["code"],
    },
    dangerous=True,
)
def run_python(code: str, timeout_seconds: int = 10, context: dict | None = None) -> str:
    """Eksekusi kode tanpa shell; keputusan approval tetap fail-closed.

    Ini bukan sandbox: kode yang disetujui berjalan dengan hak akses user saat ini.
    Karena itu mode `smart` juga meminta approval, dan tidak ada approval berarti
    kode tidak dijalankan (mis. pada gateway/one-shot noninteraktif).
    """
    context = context or {}
    if not isinstance(code, str) or not code.strip():
        return "ERROR: code tidak boleh kosong."
    if len(code) > MAX_CODE_CHARS:
        return f"ERROR: code dibatasi {MAX_CODE_CHARS} karakter."

    mode = str(context.get("approval_mode", "smart")).lower()
    if mode == "never":
        return "DITOLAK: Python runner diblokir karena arbitrary code berbahaya (approval_mode=never)."

    try:
        timeout = min(max(int(timeout_seconds), 1), MAX_TIMEOUT_SECONDS)
    except (TypeError, ValueError):
        timeout = 10
    approve = context.get("approve")
    request = f"run_python: jalankan kode Python (maks {timeout} detik):\n{_approval_display(code)}"
    if approve is None:
        return (
            "PERLU APPROVAL: run_python selalu meminta persetujuan eksplisit dan tidak berjalan "
            "dari mode noninteraktif. Buka `laction chat` untuk menyetujui setelah meninjau kode."
        )
    try:
        if not approve(request):
            return "DITOLAK: user tidak menyetujui eksekusi Python."
    except Exception as exc:  # noqa: BLE001 — approval harus fail-closed
        return f"DITOLAK: gagal meminta approval: {exc}"

    try:
        proc = subprocess.run(
            [sys.executable, "-B", "-c", code],
            cwd=Path.cwd(),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            check=False,
        )
        output = "\n".join(part for part in (proc.stdout.strip(), proc.stderr.strip()) if part)
        return truncate(f"[exit={proc.returncode}]\n{output or '(tidak ada output)'}", 6000)
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        output = "\n".join(part for part in (stdout.strip(), stderr.strip()) if part)
        suffix = f"\nOutput parsial:\n{output}" if output else ""
        return truncate(f"TIMEOUT: Python melebihi {timeout} detik.{suffix}", 6000)
    except OSError as exc:
        return f"ERROR menjalankan Python: {exc}"
