"""Explicitly approved Python runner for local experiments and debugging."""
from __future__ import annotations

import subprocess
import sys

from ..sandbox import DEFAULT_DOCKER_IMAGE, DockerExecutor, resolve_execution_backend
from ..utils import truncate
from . import file_tools
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
    "Jalankan potongan Python lokal untuk eksperimen/debug. Arbitrary code, BUKAN sandbox (kecuali sandbox_mode=docker aktif); selalu perlu persetujuan eksplisit.",
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

    Pada `sandbox_mode=none` kode berjalan lokal dengan hak akses user saat ini.
    Pada `sandbox_mode=docker` eksekusi dijalankan via `DockerExecutor` terbatas
    (`--network none`, `--read-only`, `--cap-drop ALL`) dan gagal tertutup bila Docker mati.
    """
    context = context or {}
    if not isinstance(code, str) or not code.strip():
        return "ERROR: code tidak boleh kosong."
    if len(code) > MAX_CODE_CHARS:
        return f"ERROR: code dibatasi {MAX_CODE_CHARS} karakter."

    cfg = context.get("cfg")
    mode = str(context.get("approval_mode", getattr(cfg, "approval_mode", "smart"))).lower()
    if mode == "never":
        return "DITOLAK: Python runner diblokir karena arbitrary code berbahaya (approval_mode=never)."

    sandbox_mode = context.get("sandbox_mode", getattr(cfg, "sandbox_mode", "none"))
    docker_image = getattr(cfg, "docker_image", DEFAULT_DOCKER_IMAGE)
    backend, err = resolve_execution_backend(sandbox_mode)
    if backend == "blocked":
        return err

    try:
        timeout = min(max(int(timeout_seconds), 1), MAX_TIMEOUT_SECONDS)
    except (TypeError, ValueError):
        timeout = 10
    approve = context.get("approve")
    target_desc = "via Docker container" if backend == "docker" else "lokal"
    request = f"run_python ({target_desc}): jalankan kode Python (maks {timeout} detik):\n{_approval_display(code)}"
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

    ws = file_tools.get_workspace(context)
    try:
        if backend == "docker":
            proc = DockerExecutor(docker_image).run(
                ["python3", "-B", "-c", code],
                workspace=ws,
                timeout=timeout,
                writable=False,
            )
            output = "\n".join(part for part in (proc.stdout.strip(), proc.stderr.strip()) if part)
            return truncate(f"[backend=docker exit={proc.returncode}]\n{output or '(tidak ada output)'}", 6000)

        proc = subprocess.run(
            [sys.executable, "-B", "-c", code],
            cwd=ws,
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
