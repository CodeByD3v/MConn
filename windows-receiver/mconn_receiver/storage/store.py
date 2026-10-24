"""Staging + atomic placement into the inbox."""
from __future__ import annotations

import os
import shutil
import threading
from collections.abc import Callable
from pathlib import Path

from ..config import Settings
from .filenames import resolve_conflict, sanitize_filename


class InboxStore:
    def __init__(self, settings: Settings) -> None:
        self.inbox = settings.inbox_dir
        self.staging = settings.staging_dir
        self.inbox.mkdir(parents=True, exist_ok=True)
        self.staging.mkdir(parents=True, exist_ok=True)
        self._commit_lock = threading.Lock()

    def staging_path(self, transfer_id: str) -> Path:
        return self.staging / f"{transfer_id}.part"

    def free_bytes(self) -> int:
        return shutil.disk_usage(self.staging).free

    def commit(self, part: Path, desired_name: str, on_reserved: Callable[[str, Path], None]) -> tuple[str, Path]:
        """Pick a non-colliding name, record it, then atomically move the file into the inbox.

        on_reserved runs BEFORE the move so a crash in between can be reconciled at startup.
        """
        with self._commit_lock:
            stored = sanitize_filename(desired_name)
            dest = resolve_conflict(self.inbox, stored)
            on_reserved(dest.name, dest)
            os.replace(part, dest)  # same volume => atomic
            return dest.name, dest

    def purge_unknown_parts(self, active_ids: set[str]) -> int:
        removed = 0
        for p in self.staging.glob("*.part"):
            if p.stem not in active_ids:
                p.unlink(missing_ok=True)
                removed += 1
        return removed
