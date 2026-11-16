"""
Backend eksekusi terisolasi opsional berbasis Docker (`DockerExecutor`).

Tetap stdlib-only (memanggil binary `docker` via `subprocess` tanpa SDK tambahan).
Mengikuti prinsip least-privilege container (NIST SP 800-190):
- `--network none` (tanpa akses jaringan keluar)
- `--read-only` root filesystem + `/tmp` terbatas (`noexec,nosuid,size=64m`)
- `--cap-drop ALL` & `--security-opt no-new-privileges`
- `--pids-limit 64`, `--memory 256m`, `--cpus 1.0`
- `--user 65534:65534` (unprivileged `nobody`)
- Tanpa meneruskan environment variable / secret host ke dalam container.

Catatan jujur: container berbagi kernel dengan host (bukan VM penuh), dan jika
workspace di-mount writable, perubahan pada workspace tetap berdampak nyata.
Karena itu approval interaktif tetap diwajibkan.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

DEFAULT_DOCKER_IMAGE = "python:3.11-slim"


def _host_docker_env() -> dict[str, str]:
    """Environment minimal untuk binary `docker` di host tanpa membocorkan API key agent."""
    allowed = ("PATH", "HOME", "USER", "DOCKER_HOST", "DOCKER_CONFIG", "DOCKER_CERT_PATH", "DOCKER_TLS_VERIFY", "XDG_RUNTIME_DIR")
    return {k: os.environ[k] for k in allowed if k in os.environ}


class DockerExecutor:
    def __init__(self, image: str = DEFAULT_DOCKER_IMAGE):
        self.image = (image or DEFAULT_DOCKER_IMAGE).strip()

    @staticmethod
    def has_docker_cli() -> bool:
        return shutil.which("docker") is not None

    @classmethod
    def is_daemon_ready(cls, timeout: float = 2.0) -> bool:
        if not cls.has_docker_cli():
            return False
        try:
            proc = subprocess.run(
                ["docker", "version", "--format", "{{.Server.Version}}"],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=max(0.5, float(timeout)),
                env=_host_docker_env(),
                check=False,
            )
            return proc.returncode == 0 and bool(proc.stdout.strip())
        except (OSError, subprocess.SubprocessError):
            return False

    def build_command(
        self,
        argv: list[str],
        workspace: Path,
        writable: bool = False,
    ) -> list[str]:
        if not argv:
            raise ValueError("argv container tidak boleh kosong")
        ws = Path(workspace).expanduser().resolve()
        mount_mode = "rw" if writable else "ro"
        return [
            "docker", "run", "--rm", "-i",
            "--network", "none",
            "--read-only",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--pids-limit", "64",
            "--memory", "256m",
            "--cpus", "1.0",
            "--user", "65534:65534",
            "--env", "HOME=/tmp",
            "--env", "PYTHONDONTWRITEBYTECODE=1",
            "--volume", f"{ws}:/workspace:{mount_mode}",
            "--workdir", "/workspace",
            self.image,
            *argv,
        ]

    def run(
        self,
        argv: list[str],
        workspace: Path,
        timeout: int = 30,
        writable: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        cmd = self.build_command(argv=argv, workspace=workspace, writable=writable)
        return subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            env=_host_docker_env(),
            check=False,
        )


def resolve_execution_backend(sandbox_mode: str = "none") -> tuple[str, str]:
    """Tentukan backend ('local' | 'docker' | 'blocked') sesuai sandbox_mode."""
    mode = (sandbox_mode or "none").strip().lower()
    if mode == "none":
        return ("local", "")
    if mode == "docker":
        if not DockerExecutor.has_docker_cli():
            return (
                "blocked",
                "DITOLAK: sandbox_mode=docker aktif tetapi binary 'docker' tidak ditemukan (fail-closed).",
            )
        if not DockerExecutor.is_daemon_ready():
            return (
                "blocked",
                "DITOLAK: sandbox_mode=docker aktif tetapi Docker daemon tidak merespons (fail-closed).",
            )
        return ("docker", "")
    if mode == "auto":
        if DockerExecutor.is_daemon_ready():
            return ("docker", "")
        return ("local", "")
    return ("blocked", f"DITOLAK: sandbox_mode tidak dikenal: {mode}")
