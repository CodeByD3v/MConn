"""SQLite access + numbered migrations. Schema mirrors the PC_* entities in DATABASE.mmd."""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from ..util import now_ms

MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
        CREATE TABLE devices (
            device_id    TEXT PRIMARY KEY,
            name         TEXT NOT NULL,
            public_key   TEXT NOT NULL,
            status       TEXT NOT NULL CHECK (status IN ('ACTIVE','REVOKED')),
            paired_at    INTEGER NOT NULL,
            revoked_at   INTEGER,
            last_seen_at INTEGER
        );
        CREATE TABLE pairing_sessions (
            session_id          TEXT PRIMARY KEY,
            token_hash          TEXT NOT NULL UNIQUE,
            created_at          INTEGER NOT NULL,
            expires_at          INTEGER NOT NULL,
            consumed_at         INTEGER,
            pending_device_name TEXT,
            pending_public_key  TEXT,
            outcome             TEXT NOT NULL DEFAULT 'PENDING'
                                CHECK (outcome IN ('PENDING','APPROVED','DENIED','EXPIRED')),
            resulting_device_id TEXT REFERENCES devices(device_id)
        );
        CREATE TABLE transfers (
            transfer_id    TEXT PRIMARY KEY,
            device_id      TEXT NOT NULL REFERENCES devices(device_id),
            original_name  TEXT NOT NULL,
            stored_name    TEXT,
            size_bytes     INTEGER NOT NULL,
            sha256         TEXT NOT NULL,
            mime           TEXT,
            bytes_received INTEGER NOT NULL DEFAULT 0,
            state          TEXT NOT NULL CHECK (state IN ('UPLOADING','COMMITTED','FAILED')),
            staging_path   TEXT,
            final_path     TEXT,
            fail_reason    TEXT,
            created_at     INTEGER NOT NULL,
            updated_at     INTEGER NOT NULL,
            committed_at   INTEGER
        );
        CREATE INDEX idx_transfers_device ON transfers(device_id, committed_at);
        CREATE TABLE nonces (
            device_id TEXT NOT NULL REFERENCES devices(device_id),
            nonce     TEXT NOT NULL,
            seen_at   INTEGER NOT NULL,
            PRIMARY KEY (device_id, nonce)
        );
        CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """,
    ),
    (
        2,
        """
        CREATE TABLE audit_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            subject_id TEXT,
            occurred_at INTEGER NOT NULL,
            detail TEXT
        );
        CREATE INDEX idx_audit_events_time ON audit_events(occurred_at);
        """,
    ),
]


class Database:
    """One shared connection guarded by a re-entrant lock. Operations are short and local."""

    def __init__(self, path: Path | str) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA journal_mode=WAL")
        self.migrate()

    def migrate(self) -> None:
        with self._lock:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at INTEGER NOT NULL)"
            )
            done = {r["version"] for r in self._conn.execute("SELECT version FROM schema_migrations")}
            for version, sql in MIGRATIONS:
                if version in done:
                    continue
                self._conn.execute("BEGIN IMMEDIATE")
                try:
                    for stmt in filter(None, (s.strip() for s in sql.split(";"))):
                        self._conn.execute(stmt)
                    self._conn.execute(
                        "INSERT INTO schema_migrations(version, applied_at) VALUES (?,?)", (version, now_ms())
                    )
                    self._conn.execute("COMMIT")
                except Exception:
                    self._conn.execute("ROLLBACK")
                    raise

    def run(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, params)

    def one(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def all(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    @contextmanager
    def transaction(self):
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield self
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    def get_setting(self, key: str) -> str | None:
        row = self.one("SELECT value FROM settings WHERE key=?", (key,))
        return row["value"] if row else None

    def set_setting(self, key: str, value: str) -> None:
        self.run("INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

    def audit(self, event_type: str, subject_id: str | None = None, detail: str | None = None) -> None:
        """Persist security-relevant metadata only; callers must never supply secrets."""
        self.run(
            "INSERT INTO audit_events(event_type, subject_id, occurred_at, detail) VALUES (?,?,?,?)",
            (event_type, subject_id, now_ms(), detail),
        )

    def close(self) -> None:
        with self._lock:
            self._conn.close()
