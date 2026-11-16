"""Tools cron: jadwalkan tugas berulang (disimpan ke cron.json)."""
from __future__ import annotations

from .registry import get_registry

reg = get_registry()


@reg.register(
    "cron_add",
    "Tambah tugas terjadwal. interval_seconds = jeda antar run (mis. 3600 = tiap jam).",
    {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Nama unik job"},
            "task": {"type": "string", "description": "Pesan/tugas yang dijalankan agent"},
            "interval_seconds": {"type": "integer", "description": "Jeda minimal 10 detik"},
        },
        "required": ["name", "task", "interval_seconds"],
    },
)
def cron_add(name: str, task: str, interval_seconds: int, context: dict) -> str:
    sched = (context or {}).get("cron")
    if sched is None:
        return "Scheduler tidak tersedia. Jalankan lewat 'laction gateway' atau 'laction cron start'."
    seconds = max(10, int(interval_seconds))
    sched.add_job(name, task, seconds)
    return f"Cron '{name}' ditambahkan: '{task}' tiap {seconds} detik."


@reg.register(
    "cron_list",
    "Daftar tugas terjadwal aktif.",
    {"type": "object", "properties": {}},
)
def cron_list(context: dict) -> str:
    sched = (context or {}).get("cron")
    if sched is None:
        return "Scheduler tidak tersedia."
    jobs = sched.list_jobs()
    if not jobs:
        return "(tidak ada cron job)"
    return "\n".join(
        f"- {j['name']}: {j['task']} (tiap {j['interval_seconds']}s)" for j in jobs
    )


@reg.register(
    "cron_remove",
    "Hapus tugas terjadwal berdasarkan nama.",
    {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
)
def cron_remove(name: str, context: dict) -> str:
    sched = (context or {}).get("cron")
    if sched is None:
        return "Scheduler tidak tersedia."
    before = {j["name"] for j in sched.list_jobs()}
    sched.remove_job(name)
    if name not in before:
        return f"Cron '{name}' tidak ditemukan."
    return f"Cron '{name}' dihapus."
