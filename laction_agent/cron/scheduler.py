"""
Cron Scheduler — tugas berulang berbasis interval.

Job disimpan ke `cron.json` di LACTION_HOME. Perbaikan hasil review:

- Job **tidak langsung jalan** saat `start()`; jeda pertama dihitung sejak
  job dibuat / scheduler dinyalakan (sebelumnya `_last_run` default 0
  membuat semua job fire-on-start).
- Tiap job dijalankan di thread terpisah + flag in-flight, jadi satu tugas
  lambat tidak menghentikan scheduler atau menumpuk duplikat.
- File korup/empty ditangani, bukan bikin thread mati.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Callable

from ..utils import log


class CronScheduler:
    def __init__(self, home: Path, on_run: Callable[[str], str] | None = None):
        self.file = Path(home) / "cron.json"
        self.file.parent.mkdir(parents=True, exist_ok=True)
        self.on_run = on_run
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._last_run: dict[str, float] = {}
        self._running: set[str] = set()

    def _load(self) -> list[dict]:
        if not self.file.exists():
            return []
        try:
            data = json.loads(self.file.read_text(encoding="utf-8") or "[]")
            return [j for j in data if isinstance(j, dict) and "name" in j and "task" in j]
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            log.warning("cron.json tidak terbaca, dianggap kosong: %s", self.file)
            return []

    def _save(self, jobs: list[dict]):
        self.file.write_text(json.dumps(jobs, indent=2, ensure_ascii=False), encoding="utf-8")

    def add_job(self, name: str, task: str, interval_seconds: int):
        seconds = max(1, int(interval_seconds))
        with self._lock:
            jobs = [j for j in self._load() if j.get("name") != name]
            jobs.append({"name": name, "task": task, "interval_seconds": seconds})
            self._save(jobs)
            # Mulai hitung jeda sejak job ditambahkan.
            self._last_run[name] = time.time()

    def remove_job(self, name: str):
        with self._lock:
            self._save([j for j in self._load() if j.get("name") != name])
            self._last_run.pop(name, None)

    def list_jobs(self) -> list[dict]:
        return self._load()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        now = time.time()
        with self._lock:
            for job in self.list_jobs():
                self._last_run.setdefault(job["name"], now)
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="laction-cron")
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _trigger(self, job: dict):
        name = job["name"]
        with self._lock:
            if name in self._running or len(self._running) >= 3:
                log.warning("Cron %r dilewati: sudah berjalan atau batas 3 job aktif tercapai", name)
                return
            self._running.add(name)

        def _worker():
            try:
                if self.on_run:
                    self.on_run(job["task"])
            except Exception as e:  # noqa: BLE001 — cron tidak boleh mati karena 1 job
                log.warning("Cron '%s' gagal: %s", name, e)
            finally:
                with self._lock:
                    self._running.discard(name)

        threading.Thread(target=_worker, daemon=True, name=f"laction-cron-{name}").start()

    def _loop(self):
        while not self._stop.is_set():
            now = time.time()
            for job in self.list_jobs():
                try:
                    interval = max(1, int(job.get("interval_seconds", 3600)))
                except (TypeError, ValueError):
                    interval = 3600
                last = self._last_run.get(job["name"], now)
                if now - last >= interval:
                    self._last_run[job["name"]] = now
                    self._trigger(job)
            self._stop.wait(1)
