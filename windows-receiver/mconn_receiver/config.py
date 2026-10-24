"""Settings: defaults < <data_dir>/config.toml < MCONN_* environment < explicit overrides."""
from __future__ import annotations

import os
import platform
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

GiB = 1024**3
_INTS = {
    "port", "max_file_bytes", "min_free_bytes", "pairing_ttl_seconds",
    "staging_ttl_hours", "clock_skew_seconds", "max_chunk_bytes",
}
_FLOATS = {"pairing_wait_seconds", "pairing_poll_seconds"}
_LISTS = {"bind_hosts", "advertise_hosts"}


def _default_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    return Path(base) / "MConn" if base else Path.home() / ".local" / "share" / "mconn"


def _default_inbox_dir() -> Path:
    if os.name == "nt" and Path("D:/").exists():
        return Path("D:/MConn/Inbox")
    return Path.home() / "MConn" / "Inbox"


@dataclass
class Settings:
    data_dir: Path = field(default_factory=_default_data_dir)
    inbox_dir: Path = field(default_factory=_default_inbox_dir)
    staging_dir: Path | None = None  # must share a volume with inbox_dir (atomic move)
    port: int = 8443
    pc_name: str = field(default_factory=platform.node)
    max_file_bytes: int = 4 * GiB
    min_free_bytes: int = 1 * GiB
    pairing_ttl_seconds: int = 300
    pairing_wait_seconds: float = 120.0
    pairing_poll_seconds: float = 0.5
    staging_ttl_hours: int = 24
    clock_skew_seconds: int = 300
    max_chunk_bytes: int = 8 * 1024 * 1024
    bind_hosts: list[str] | None = None       # None = auto-detect private interfaces only
    advertise_hosts: list[str] | None = None  # None = auto-detect

    def __post_init__(self) -> None:
        self.data_dir = Path(self.data_dir)
        self.inbox_dir = Path(self.inbox_dir)
        self.staging_dir = Path(self.staging_dir) if self.staging_dir else self.inbox_dir / ".staging"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "mconn.db"

    @property
    def tls_dir(self) -> Path:
        return self.data_dir / "tls"


def _coerce(name: str, value):
    if name in _INTS:
        return int(value)
    if name in _FLOATS:
        return float(value)
    if name in _LISTS and isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    return value


def load_settings(**overrides) -> Settings:
    values: dict = {}
    data_dir = Path(overrides.get("data_dir") or os.environ.get("MCONN_DATA_DIR") or _default_data_dir())
    cfg = data_dir / "config.toml"
    if cfg.exists():
        values.update(tomllib.loads(cfg.read_text(encoding="utf-8")))
    for f in fields(Settings):
        env = os.environ.get(f"MCONN_{f.name.upper()}")
        if env is not None:
            values[f.name] = env
    values.update(overrides)
    values["data_dir"] = data_dir
    return Settings(**{k: _coerce(k, v) for k, v in values.items()})
