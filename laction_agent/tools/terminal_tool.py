"""Tool terminal: jalankan perintah shell dengan approval & timeout."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .registry import get_registry

# Frasa berbahaya. Dicek sebagai token utuh di seluruh command, bukan cuma
# di awal string — supaya `echo aman; rm -rf /tmp/x` tidak lolos.
DANGEROUS = (
    "rm -rf", "rm -fr", "rm -r /", "rm --recursive-force",
    "mkfs", "dd if=", "dd of=", ":(){", "shutdown", "reboot", "halt", "poweroff",
    "chmod -r /", "chown -r /", "curl", "wget", "sudo",
    "git push --force", "git push -f", ">/dev/sd",
)
_DANGEROUS_RE = tuple(
    re.compile(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", re.IGNORECASE)
    for phrase in DANGEROUS
)


def _is_dangerous(cmd: str) -> bool:
    """Deteksi perintah berbahaya, termasuk yang disisipkan lewat chaining.

    Review menemukan bypass pada versi lama: `echo $(curl ...)`,
    ``echo `rm -rf /tmp/x` ``, dan `printf x; dd if=...` lolos karena
    pengecekan hanya `startswith` / substring berspasi ganda.
    """
    text = (cmd or "").lower().strip()
    if not text:
        return False
    # Substitusi perintah menyembunyikan eksekusi di dalam argumen.
    if "$(" in text or "`" in text:
        return True
    return any(pattern.search(text) for pattern in _DANGEROUS_RE)


reg = get_registry()


@reg.register(
    "run_terminal",
    "Jalankan perintah shell (mis. ls, python, git). Timeout 30 detik.",
    {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]},
    dangerous=True,
)
def run_terminal(command: str, context: dict) -> str:
    context = context or {}
    mode = context.get("approval_mode", "smart")
    approve = context.get("approve")
    dangerous = _is_dangerous(command)

    if dangerous and mode == "never":
        return "DITOLAK: perintah berbahaya diblokir (approval_mode=never)."

    needs_approval = mode == "always" or (mode == "smart" and dangerous)
    if needs_approval:
        if approve is None:
            return (
                f"PERLU APPROVAL: perintah '{command}' tidak dijalankan otomatis. "
                "Pakai CLI interaktif, atau set approval_mode=smart/never dengan sadar."
            )
        try:
            if not approve(command):
                return "DITOLAK: user tidak menyetujui perintah."
        except Exception as e:  # noqa: BLE001
            return f"DITOLAK: gagal meminta approval: {e}"

    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=Path.cwd(),
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        return f"[exit={proc.returncode}]\n{out.strip() or '(tidak ada output)'}"
    except subprocess.TimeoutExpired:
        return "TIMEOUT: perintah melebihi 30 detik."
    except Exception as e:  # noqa: BLE001
        return f"ERROR: {e}"
