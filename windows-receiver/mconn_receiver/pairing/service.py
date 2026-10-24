"""Pairing sessions and device registry. The PC is the sole authority on trust."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import secrets
import uuid
from dataclasses import dataclass, field

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import load_der_public_key

from ..config import Settings
from ..database.db import Database
from ..errors import MConnError
from ..util import b64url_encode, now_ms


@dataclass
class Identity:
    pc_id: str
    pc_name: str
    cert_sha256: str
    port: int
    hosts: list[str] = field(default_factory=list)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def validate_public_key(b64: str) -> None:
    """Accept only base64(X.509 SubjectPublicKeyInfo) P-256 keys (what Android's Keystore exports)."""
    try:
        key = load_der_public_key(base64.b64decode(b64, validate=True))
    except Exception as exc:
        raise MConnError(400, "INVALID_REQUEST", "public_key is not valid base64 DER") from exc
    if not isinstance(key, ec.EllipticCurvePublicKey) or key.curve.name != "secp256r1":
        raise MConnError(400, "INVALID_REQUEST", "public_key must be an EC P-256 key")


class PairingService:
    def __init__(self, db: Database, settings: Settings, identity: Identity) -> None:
        self.db, self.settings, self.identity = db, settings, identity

    # ---- QR / session -------------------------------------------------
    def create_session(self) -> dict:
        token = secrets.token_urlsafe(32)
        session_id = str(uuid.uuid4())
        created = now_ms()
        expires = created + self.settings.pairing_ttl_seconds * 1000
        self.db.run(
            "INSERT INTO pairing_sessions(session_id, token_hash, created_at, expires_at) VALUES (?,?,?,?)",
            (session_id, _hash_token(token), created, expires),
        )
        payload = {
            "v": 1,
            "pc_id": self.identity.pc_id,
            "pc_name": self.identity.pc_name,
            "hosts": self.identity.hosts,
            "port": self.identity.port,
            "cert_sha256": self.identity.cert_sha256,
            "token": token,
            "exp": expires // 1000,
        }
        encoded = b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
        return {"session_id": session_id, "payload": encoded, "expires_at": expires}

    # ---- phone side ---------------------------------------------------
    def claim(self, token: str, device_name: str, public_key: str) -> str:
        """Consume the single-use token and mark the session awaiting approval. Returns session_id."""
        if not isinstance(token, str) or not isinstance(device_name, str) or not isinstance(public_key, str):
            raise MConnError(400, "INVALID_REQUEST", "token, device_name and public_key are required")
        device_name = device_name.strip()[:80]
        if not device_name:
            raise MConnError(400, "INVALID_REQUEST", "device_name is required")
        validate_public_key(public_key)
        with self.db.transaction():
            row = self.db.one("SELECT * FROM pairing_sessions WHERE token_hash=?", (_hash_token(token),))
            if row is None or row["consumed_at"] is not None or row["expires_at"] < now_ms():
                raise MConnError(403, "PAIRING_INVALID", "Pairing code is invalid, expired or already used")
            self.db.run(
                "UPDATE pairing_sessions SET consumed_at=?, pending_device_name=?, pending_public_key=? WHERE session_id=?",
                (now_ms(), device_name, public_key, row["session_id"]),
            )
            return row["session_id"]

    async def wait_for_decision(self, session_id: str) -> dict:
        deadline = asyncio.get_running_loop().time() + self.settings.pairing_wait_seconds
        while True:
            row = self.db.one("SELECT * FROM pairing_sessions WHERE session_id=?", (session_id,))
            if row["outcome"] == "APPROVED":
                return {"device_id": row["resulting_device_id"], "pc_id": self.identity.pc_id, "pc_name": self.identity.pc_name}
            if row["outcome"] in ("DENIED", "EXPIRED"):
                raise MConnError(403, "PAIRING_DENIED", "Pairing was not approved")
            if asyncio.get_running_loop().time() >= deadline:
                self.db.run("UPDATE pairing_sessions SET outcome='EXPIRED' WHERE session_id=? AND outcome='PENDING'", (session_id,))
                raise MConnError(408, "PAIRING_PENDING", "Pairing was not approved in time", retryable=False)
            await asyncio.sleep(self.settings.pairing_poll_seconds)

    # ---- PC side (admin) ----------------------------------------------
    def pending(self) -> list[dict]:
        rows = self.db.all(
            "SELECT session_id, pending_device_name FROM pairing_sessions "
            "WHERE outcome='PENDING' AND pending_public_key IS NOT NULL"
        )
        return [{"session_id": r["session_id"], "device_name": r["pending_device_name"]} for r in rows]

    def approve(self, session_id: str) -> str:
        with self.db.transaction():
            row = self.db.one("SELECT * FROM pairing_sessions WHERE session_id=?", (session_id,))
            if row is None or row["outcome"] != "PENDING" or not row["pending_public_key"]:
                raise MConnError(404, "PAIRING_NOT_PENDING", "No pending pairing request with that id")
            device_id = str(uuid.uuid4())
            self.db.run(
                "INSERT INTO devices(device_id, name, public_key, status, paired_at) VALUES (?,?,?,'ACTIVE',?)",
                (device_id, row["pending_device_name"], row["pending_public_key"], now_ms()),
            )
            self.db.run(
                "UPDATE pairing_sessions SET outcome='APPROVED', resulting_device_id=? WHERE session_id=?",
                (device_id, session_id),
            )
        return device_id

    def deny(self, session_id: str) -> None:
        cur = self.db.run(
            "UPDATE pairing_sessions SET outcome='DENIED' WHERE session_id=? AND outcome='PENDING'", (session_id,)
        )
        if cur.rowcount == 0:
            raise MConnError(404, "PAIRING_NOT_PENDING", "No pending pairing request with that id")

    def list_devices(self) -> list[dict]:
        rows = self.db.all("SELECT device_id, name, status, paired_at, last_seen_at FROM devices ORDER BY paired_at DESC")
        return [dict(r) for r in rows]

    def revoke(self, device_id: str) -> None:
        cur = self.db.run(
            "UPDATE devices SET status='REVOKED', revoked_at=? WHERE device_id=? AND status='ACTIVE'",
            (now_ms(), device_id),
        )
        if cur.rowcount == 0:
            raise MConnError(404, "DEVICE_UNKNOWN", "No active device with that id")
