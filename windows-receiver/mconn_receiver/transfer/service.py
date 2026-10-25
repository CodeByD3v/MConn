"""Upload sessions: create/resume, stream to staging, verify, commit atomically, return receipts."""
from __future__ import annotations

import asyncio
import hashlib
import os
import re
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from ..config import Settings
from ..database.db import Database
from ..errors import MConnError
from ..storage.store import InboxStore
from ..util import iso_utc, now_ms

_SHA_RE = re.compile(r"^[0-9a-f]{64}$")


def _parse_id(value) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, AttributeError, TypeError):
        raise MConnError(400, "INVALID_REQUEST", "transfer_id must be a UUID") from None


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


class TransferService:
    def __init__(self, db: Database, settings: Settings, store: InboxStore) -> None:
        self.db, self.settings, self.store = db, settings, store
        self._busy: set[str] = set()

    # ---- views --------------------------------------------------------
    def receipt(self, row) -> dict:
        return {
            "transfer_id": row["transfer_id"],
            "state": "COMMITTED",
            "stored_name": row["stored_name"],  # never the absolute path
            "size": row["size_bytes"],
            "sha256": row["sha256"],
            "committed_at": iso_utc(row["committed_at"]),
        }

    def view(self, row) -> dict:
        out = {
            "transfer_id": row["transfer_id"],
            "state": row["state"],
            "bytes_received": row["bytes_received"],
            "max_chunk_bytes": self.settings.max_chunk_bytes,
        }
        if row["state"] == "COMMITTED":
            out["receipt"] = self.receipt(row)
        if row["state"] == "FAILED":
            out["fail_reason"] = row["fail_reason"]
        return out

    def _row(self, tid: str):
        return self.db.one("SELECT * FROM transfers WHERE transfer_id=?", (tid,))

    def _owned(self, device_id: str, transfer_id: str):
        tid = _parse_id(transfer_id)
        row = self._row(tid)
        if row is None or row["device_id"] != device_id:
            raise MConnError(404, "TRANSFER_NOT_FOUND", "Unknown transfer")
        return row

    def _set_received(self, tid: str, n: int) -> None:
        self.db.run("UPDATE transfers SET bytes_received=?, updated_at=? WHERE transfer_id=?", (n, now_ms(), tid))

    # ---- create / status ---------------------------------------------
    def create(self, device_id: str, data: dict) -> tuple[int, dict]:
        tid = _parse_id(data.get("transfer_id"))
        name, size, sha = data.get("name"), data.get("size"), str(data.get("sha256", "")).lower()
        mime = data.get("mime")
        if not isinstance(name, str) or not name.strip() or len(name) > 1024:
            raise MConnError(400, "INVALID_REQUEST", "name is required")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise MConnError(400, "INVALID_REQUEST", "size must be a non-negative integer")
        if not _SHA_RE.match(sha):
            raise MConnError(400, "INVALID_REQUEST", "sha256 must be 64 lowercase hex characters")
        if mime is not None and (not isinstance(mime, str) or len(mime) > 255):
            raise MConnError(400, "INVALID_REQUEST", "mime is invalid")

        existing = self._row(tid)
        if existing is not None:
            if existing["device_id"] != device_id or existing["size_bytes"] != size or existing["sha256"] != sha:
                raise MConnError(409, "TRANSFER_CONFLICT", "transfer_id already used with different content")
            if existing["state"] == "FAILED":
                self.store.staging_path(tid).unlink(missing_ok=True)
                self.db.run(
                    "UPDATE transfers SET state='UPLOADING', bytes_received=0, fail_reason=NULL, updated_at=? WHERE transfer_id=?",
                    (now_ms(), tid),
                )
                existing = self._row(tid)
            return 200, self.view(existing)

        if size > self.settings.max_file_bytes:
            raise MConnError(413, "FILE_TOO_LARGE", "File exceeds the configured size limit")
        if self.store.free_bytes() - size < self.settings.min_free_bytes:
            raise MConnError(507, "INSUFFICIENT_STORAGE", "Not enough free disk space on the PC", retryable=True)
        now = now_ms()
        self.db.run(
            "INSERT INTO transfers(transfer_id, device_id, original_name, size_bytes, sha256, mime, state, "
            "staging_path, created_at, updated_at) VALUES (?,?,?,?,?,?, 'UPLOADING', ?, ?, ?)",
            (tid, device_id, name, size, sha, mime, str(self.store.staging_path(tid)), now, now),
        )
        return 201, self.view(self._row(tid))

    def status(self, device_id: str, transfer_id: str) -> dict:
        return self.view(self._owned(device_id, transfer_id))

    def inbox(self, device_id: str, limit: int) -> list[dict]:
        limit = max(1, min(limit, 200))
        rows = self.db.all(
            "SELECT * FROM transfers WHERE device_id=? AND state='COMMITTED' ORDER BY committed_at DESC LIMIT ?",
            (device_id, limit),
        )
        return [self.receipt(r) for r in rows]

    # ---- upload -------------------------------------------------------
    async def put_content(self, device_id: str, transfer_id: str, offset: int, chunks: AsyncIterator[bytes]) -> dict:
        row = self._owned(device_id, transfer_id)
        tid = row["transfer_id"]
        if row["state"] == "COMMITTED":
            return self.view(row)  # idempotent: already delivered
        if row["state"] != "UPLOADING":
            raise MConnError(409, "TRANSFER_NOT_UPLOADABLE", "Transfer failed; create it again to restart")
        if tid in self._busy:
            raise MConnError(409, "TRANSFER_BUSY", "Another upload for this transfer is in progress", retryable=True)
        self._busy.add(tid)
        try:
            return await self._receive(row, offset, chunks)
        finally:
            self._busy.discard(tid)

    async def _receive(self, row, offset: int, chunks: AsyncIterator[bytes]) -> dict:
        tid, size = row["transfer_id"], row["size_bytes"]
        part = self.store.staging_path(tid)
        recorded = row["bytes_received"]
        actual = part.stat().st_size if part.exists() else 0
        if actual < recorded:  # staging file lost or truncated: trust the disk
            self._set_received(tid, actual)
            recorded = actual
        if offset != recorded:
            raise MConnError(
                409, "OFFSET_MISMATCH", f"Server offset is {recorded}", retryable=True,
                extra={"bytes_received": recorded},
            )
        written = offset
        try:
            with open(part, "r+b" if part.exists() else "wb") as f:
                f.truncate(offset)  # drop bytes from an interrupted earlier request
                f.seek(offset)
                async for chunk in chunks:
                    if written + len(chunk) > size:
                        raise MConnError(400, "INVALID_REQUEST", "Content exceeds declared size")
                    f.write(chunk)
                    written += len(chunk)
                f.flush()
                os.fsync(f.fileno())
        finally:
            self._set_received(tid, written)  # record progress even if the client disconnected
        if written < size:
            return self.view(self._row(tid))
        return await self._finalize(self._row(tid), part)

    async def _finalize(self, row, part: Path) -> dict:
        tid = row["transfer_id"]
        digest = await asyncio.to_thread(_sha256_file, part)
        if digest != row["sha256"]:
            part.unlink(missing_ok=True)
            self._set_received(tid, 0)
            raise MConnError(422, "HASH_MISMATCH", "Uploaded content does not match the declared SHA-256", retryable=True)

        def reserved(stored_name: str, dest: Path) -> None:
            self.db.run(
                "UPDATE transfers SET stored_name=?, final_path=?, updated_at=? WHERE transfer_id=?",
                (stored_name, str(dest), now_ms(), tid),
            )

        stored, _ = self.store.commit(part, row["original_name"], reserved)
        now = now_ms()
        self.db.run(
            "UPDATE transfers SET state='COMMITTED', stored_name=?, committed_at=?, updated_at=?, staging_path=NULL "
            "WHERE transfer_id=?",
            (stored, now, now, tid),
        )
        self.db.audit("TRANSFER_COMMITTED", tid, stored)
        return self.view(self._row(tid))

    # ---- startup / periodic housekeeping -----------------------------
    def reconcile(self) -> None:
        """Repair state after a crash and drop abandoned uploads."""
        cutoff = now_ms() - self.settings.staging_ttl_hours * 3600 * 1000
        active: set[str] = set()
        for r in self.db.all("SELECT * FROM transfers WHERE state='UPLOADING'"):
            tid, part, final = r["transfer_id"], self.store.staging_path(r["transfer_id"]), r["final_path"]
            if final and not part.exists() and Path(final).exists():
                now = now_ms()  # crashed after the move, before the DB update
                self.db.run(
                    "UPDATE transfers SET state='COMMITTED', committed_at=?, updated_at=?, staging_path=NULL WHERE transfer_id=?",
                    (now, now, tid),
                )
                continue
            if final:
                self.db.run("UPDATE transfers SET final_path=NULL, stored_name=NULL WHERE transfer_id=?", (tid,))
            if r["updated_at"] < cutoff:
                part.unlink(missing_ok=True)
                self.db.run(
                    "UPDATE transfers SET state='FAILED', fail_reason='expired', updated_at=? WHERE transfer_id=?",
                    (now_ms(), tid),
                )
                continue
            active.add(tid)
        self.store.purge_unknown_parts(active)
