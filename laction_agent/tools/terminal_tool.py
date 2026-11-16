"""Tool terminal: jalankan perintah shell dengan approval & timeout."""
from __future__ import annotations

import subprocess
from pathlib import Path

from .registry import get_registry

DANGEROUS = (
    "rm -rf", "mkfs", "dd ", ":(){", "shutdown", "reboot", "halt", "poweroff",
    "chmod -r /", "chown -r /", "curl", "wget", "sudo ", "git push --force",
)


def _is_dangerous(cmd: str) -> bool:
    c = f" {cmd.lower().strip()} "
    return any(f" {d} " in c or c.strip().startswith(d) for d in DANGEROUS)


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
