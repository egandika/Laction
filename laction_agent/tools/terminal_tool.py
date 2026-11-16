"""Tool terminal: jalankan perintah shell dengan approval, timeout, & DockerExecutor opsional."""
from __future__ import annotations

import re
import subprocess

from ..sandbox import DEFAULT_DOCKER_IMAGE, DockerExecutor, resolve_execution_backend
from . import file_tools
from .python_tool import _approval_display
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
    "Jalankan perintah shell (mis. ls, python, git). Timeout 30 detik; selalu perlu approval.",
    {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]},
    dangerous=True,
)
def run_terminal(command: str, context: dict) -> str:
    context = context or {}
    cfg = context.get("cfg")
    mode = context.get("approval_mode", getattr(cfg, "approval_mode", "smart"))
    sandbox_mode = context.get("sandbox_mode", getattr(cfg, "sandbox_mode", "none"))
    docker_image = getattr(cfg, "docker_image", DEFAULT_DOCKER_IMAGE)
    approve = context.get("approve")
    dangerous = _is_dangerous(command)

    if mode == "never":
        return "DITOLAK: semua perintah shell diblokir (approval_mode=never)."

    backend, err = resolve_execution_backend(sandbox_mode)
    if backend == "blocked":
        return err

    if approve is None:
        return "PERLU APPROVAL: shell tidak dijalankan otomatis. Pakai CLI interaktif untuk meninjau perintah."
    try:
        warning = " [terdeteksi berbahaya]" if dangerous else ""
        label = (
            f"Shell via Docker container (--network none, ro workspace){warning}"
            if backend == "docker"
            else f"Shell bukan sandbox{warning}"
        )
        if not approve(f"{label}:\n{_approval_display(command)}"):
            return "DITOLAK: user tidak menyetujui perintah."
    except Exception as e:  # noqa: BLE001
        return f"DITOLAK: gagal meminta approval: {e}"

    ws = file_tools.get_workspace(context)
    try:
        if backend == "docker":
            proc = DockerExecutor(docker_image).run(
                ["sh", "-c", command],
                workspace=ws,
                timeout=30,
                writable=False,
            )
            out = (proc.stdout or "") + (proc.stderr or "")
            return f"[backend=docker exit={proc.returncode}]\n{out.strip() or '(tidak ada output)'}"

        proc = subprocess.run(
            command,
            shell=True,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=ws,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        return f"[exit={proc.returncode}]\n{out.strip() or '(tidak ada output)'}"
    except subprocess.TimeoutExpired:
        return "TIMEOUT: perintah melebihi 30 detik."
    except Exception as e:  # noqa: BLE001
        return f"ERROR: {e}"
