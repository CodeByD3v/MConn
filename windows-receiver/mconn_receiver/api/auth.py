"""Per-request device authentication (DESIGN.md 5.1).

Signed string (UTF-8, '\n'-joined):  METHOD, PATH[?QUERY], TIMESTAMP, NONCE, BODY_SHA256
BODY_SHA256 = lowercase hex SHA-256 of the raw body, or the literal UNSIGNED-PAYLOAD for streamed uploads.
Signature = base64url(ECDSA-P256-SHA256, DER) as produced by Android's "SHA256withECDSA".
"""
from __future__ import annotations

import base64
import hashlib
import sqlite3

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import load_der_public_key
from fastapi import Request

from ..config import Settings
from ..database.db import Database
from ..errors import MConnError
from ..util import b64url_decode, now_ms

UNSIGNED_PAYLOAD = "UNSIGNED-PAYLOAD"


def canonical_string(method: str, path_qs: str, timestamp: str, nonce: str, body_sha256: str) -> bytes:
    return "\n".join([method.upper(), path_qs, timestamp, nonce, body_sha256]).encode()


def body_hash(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


class Authenticator:
    def __init__(self, db: Database, settings: Settings) -> None:
        self.db, self.settings = db, settings
        self._calls = 0

    def authenticate(self, request: Request, body: bytes | None) -> sqlite3.Row:
        """body=None means streamed payload (UNSIGNED-PAYLOAD)."""
        h = request.headers
        device_id, ts, nonce, sig = (
            h.get("x-mconn-device"), h.get("x-mconn-timestamp"), h.get("x-mconn-nonce"), h.get("x-mconn-signature"),
        )
        if not (device_id and ts and nonce and sig) or len(nonce) > 64:
            raise MConnError(401, "BAD_SIGNATURE", "Missing authentication headers")
        try:
            ts_ms = int(ts) * 1000
        except ValueError:
            raise MConnError(401, "BAD_SIGNATURE", "Invalid timestamp") from None
        if abs(now_ms() - ts_ms) > self.settings.clock_skew_seconds * 1000:
            raise MConnError(401, "STALE_REQUEST", "Request timestamp is outside the allowed window", retryable=True)

        device = self.db.one("SELECT * FROM devices WHERE device_id=?", (device_id,))
        if device is None:
            raise MConnError(403, "DEVICE_UNKNOWN", "This device is not paired")

        path_qs = request.url.path + (f"?{request.url.query}" if request.url.query else "")
        digest = UNSIGNED_PAYLOAD if body is None else body_hash(body)
        message = canonical_string(request.method, path_qs, ts, nonce, digest)
        try:
            key = load_der_public_key(base64.b64decode(device["public_key"]))
            key.verify(b64url_decode(sig), message, ec.ECDSA(hashes.SHA256()))
        except (InvalidSignature, ValueError, TypeError):
            raise MConnError(401, "BAD_SIGNATURE", "Signature verification failed") from None

        if device["status"] != "ACTIVE":
            raise MConnError(403, "DEVICE_REVOKED", "This device has been revoked")

        try:  # replay protection: only after the signature is proven valid
            self.db.run("INSERT INTO nonces(device_id, nonce, seen_at) VALUES (?,?,?)", (device_id, nonce, now_ms()))
        except sqlite3.IntegrityError:
            raise MConnError(401, "STALE_REQUEST", "Nonce already used", retryable=True) from None
        self.db.run("UPDATE devices SET last_seen_at=? WHERE device_id=?", (now_ms(), device_id))
        self._calls += 1
        if self._calls % 100 == 0:
            cutoff = now_ms() - 2 * self.settings.clock_skew_seconds * 1000
            self.db.run("DELETE FROM nonces WHERE seen_at < ?", (cutoff,))
        return device
