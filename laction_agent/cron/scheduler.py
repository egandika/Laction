"""
Cron Scheduler sederhana — tugas berulang berbasis interval.

Job disimpan ke cron.json di LACTION_HOME, dijalankan oleh
thread background yang memanggil callback (biasanya agent.run).
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Callable


class CronScheduler:
    def __init__(self, home: Path, on_run: Callable[[str], str] | None = None):
        self.file = Path(home) / "cron.json"
        self.file.parent.mkdir(parents=True, exist_ok=True)
        self.on_run = on_run
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._last_run: dict[str, float] = {}

    def _load(self) -> list[dict]:
        if not self.file.exists():
            return []
        try:
            return json.loads(self.file.read_text())
        except json.JSONDecodeError:
            return []

    def _save(self, jobs: list[dict]):
        self.file.write_text(json.dumps(jobs, indent=2, ensure_ascii=False))

    def add_job(self, name: str, task: str, interval_seconds: int):
        with self._lock:
            jobs = [j for j in self._load() if j["name"] != name]
            jobs.append({"name": name, "task": task, "interval_seconds": int(interval_seconds)})
            self._save(jobs)

    def remove_job(self, name: str):
        with self._lock:
            self._save([j for j in self._load() if j["name"] != name])

    def list_jobs(self) -> list[dict]:
        return self._load()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="laction-cron")
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        while not self._stop.is_set():
            now = time.time()
            for job in self.list_jobs():
                last = self._last_run.get(job["name"], 0)
                if now - last >= job["interval_seconds"]:
                    self._last_run[job["name"]] = now
                    if self.on_run:
                        try:
                            self.on_run(job["task"])
                        except Exception:  # noqa: BLE001
                            pass
            self._stop.wait(1)
