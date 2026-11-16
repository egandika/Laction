"""
Konfigurasi Laction Agent — zero-dependency.

Prioritas (dari tertinggi):
1. Environment variable proses (LACTION_*)
2. File `.env` (dibaca tanpa python-dotenv)
3. `config.yaml` di root repo (atau path dari LACTION_CONFIG / --config)
4. Default bawaan

Parser YAML minimal disediakan untuk struktur `key: value` datar.
Kalau PyYAML terpasang, otomatis dipakai.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path

ENV_MAP = {
    "LACTION_PROVIDER": "provider",
    "LACTION_MODEL": "model",
    "LACTION_API_BASE": "api_base",
    "LACTION_API_KEY": "api_key",
    "LACTION_HOME": "home",
    "LACTION_MAX_ITERATIONS": "max_iterations",
    "LACTION_CONTEXT_LIMIT": "context_limit",
    "LACTION_APPROVAL_MODE": "approval_mode",
    "LACTION_CRON_ENABLED": "cron_enabled",
}

VALID_PROVIDERS = {
    "mock", "openai", "openrouter", "ollama", "nous", "openai_compat", "custom"
}
VALID_APPROVAL_MODES = {"smart", "always", "never"}


@dataclass
class Config:
    provider: str = "mock"
    model: str = "mock-laction-1"
    api_base: str = ""
    api_key: str = ""
    home: str = "./data"
    max_iterations: int = 10
    context_limit: int = 8000
    approval_mode: str = "smart"  # smart | always | never
    cron_enabled: bool = True

    @classmethod
    def load(cls, config_path: str | Path | None = None) -> "Config":
        # Gabungkan .env lalu environment proses (proses menang).
        file_env = {
            k: v for k, v in _load_dotenv(Path(".env")).items()
            if k.startswith("LACTION_")
        }
        process_env = {
            k: v for k, v in os.environ.items()
            if k.startswith("LACTION_")
        }
        env = {**file_env, **process_env}

        cfg = cls()
        path_value = config_path or env.get("LACTION_CONFIG")
        path = Path(path_value) if path_value else Path("config.yaml")
        if path.exists():
            for key, value in _load_yaml_minimal(path).items():
                if hasattr(cfg, key) and value not in ("", None):
                    setattr(cfg, key, _coerce(getattr(cfg, key), value))

        for env_key, attr in ENV_MAP.items():
            if env_key in env and env[env_key] != "":
                setattr(cfg, attr, _coerce(getattr(cfg, attr), env[env_key]))

        return cfg.validate()

    def validate(self) -> "Config":
        self.provider = self.provider.strip().lower()
        self.approval_mode = self.approval_mode.strip().lower()
        if self.provider not in VALID_PROVIDERS:
            raise ValueError(
                f"Provider tidak dikenal: {self.provider}. "
                f"Pilihan: {', '.join(sorted(VALID_PROVIDERS))}"
            )
        if self.approval_mode not in VALID_APPROVAL_MODES:
            raise ValueError(
                f"approval_mode harus salah satu dari: {', '.join(sorted(VALID_APPROVAL_MODES))}"
            )
        if self.max_iterations < 1:
            raise ValueError("max_iterations minimal 1")
        if self.context_limit < 1000:
            raise ValueError("context_limit minimal 1000 token")
        return self

    def as_dict(self, redact: bool = True) -> dict:
        data = asdict(self)
        if redact and data.get("api_key"):
            key = data["api_key"]
            data["api_key"] = f"***{key[-4:]}" if len(key) > 4 else "***"
        return data

    def warnings(self) -> list[str]:
        out: list[str] = []
        if self.provider in {"openai", "openrouter", "nous"} and not self.api_key:
            out.append("LACTION_API_KEY belum diisi — provider kemungkinan besar akan menolak request.")
        if self.provider != "mock" and self.model.startswith("mock"):
            out.append("LACTION_MODEL masih 'mock-laction-1'; ganti ke model asli untuk provider ini.")
        if self.approval_mode == "never":
            out.append(
                "approval_mode=never menonaktifkan prompt persetujuan; "
                "perintah berbahaya tetap diblokir."
            )
        if self.provider == "ollama" and (
            not self.api_base
            or any(h in self.api_base for h in ("localhost", "127.0.0.1", "::1"))
        ):
            out.append(
                "Gateway yang berjalan di container tidak bisa menjangkau localhost host; "
                "pakai alamat jaringan Ollama."
            )
        return out


def _coerce(current, raw):
    if isinstance(current, bool):
        return str(raw).strip().lower() in ("1", "true", "yes", "on", "ya")
    if isinstance(current, int):
        try:
            return int(str(raw).strip())
        except (ValueError, TypeError):
            return current
    return str(raw)


def _strip_value(raw: str) -> str:
    """Ambil nilai, hormati tanda kutip, buang komentar inline."""
    value = raw.strip()
    if value[:1] in ("'", '"'):
        quote = value[0]
        end = value.find(quote, 1)
        return value[1:end] if end > 0 else value[1:]
    return value.split("#", 1)[0].strip()


def _load_yaml_minimal(path: Path) -> dict:
    try:
        import yaml  # type: ignore

        with path.open(encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        pass

    data: dict = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, raw = line.partition(":")
        value = _strip_value(raw)
        if value != "":
            data[key.strip()] = value
    return data


def _load_dotenv(path: Path) -> dict:
    if not path.exists():
        return {}
    data: dict = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[7:].strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, raw = line.partition("=")
        data[key.strip()] = _strip_value(raw)
    return data
