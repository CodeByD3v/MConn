from __future__ import annotations

import base64
import hashlib
import secrets
import threading
import time
import uuid

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from mconn_receiver.api.app import create_app
from mconn_receiver.api.auth import UNSIGNED_PAYLOAD, body_hash, canonical_string
from mconn_receiver.config import Settings
from mconn_receiver.util import b64url_encode

ADMIN = {"X-MConn-Admin": "1"}


class FakePhone:
    """Plays the Android side: P-256 key, signed requests."""

    def __init__(self, name: str = "Test Phone") -> None:
        self.name = name
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.public_b64 = base64.b64encode(
            self.key.public_key().public_bytes(
                serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
            )
        ).decode()
        self.device_id: str | None = None

    def headers(self, method: str, path_qs: str, body: bytes | None, *, ts: int | None = None, nonce: str | None = None) -> dict:
        ts_s = str(ts if ts is not None else int(time.time()))
        nonce = nonce or secrets.token_urlsafe(16)
        digest = UNSIGNED_PAYLOAD if body is None else body_hash(body)
        sig = self.key.sign(canonical_string(method, path_qs, ts_s, nonce, digest), ec.ECDSA(hashes.SHA256()))
        return {
            "X-MConn-Device": self.device_id or "",
            "X-MConn-Timestamp": ts_s,
            "X-MConn-Nonce": nonce,
            "X-MConn-Signature": b64url_encode(sig),
        }

    def call(self, client: TestClient, method: str, path: str, *, json_body: dict | None = None,
             content: bytes | None = None, extra: dict | None = None, **hk):
        import json as _json

        if json_body is not None:
            raw, signed = _json.dumps(json_body).encode(), None
            signed = raw
        elif content is not None:
            raw, signed = content, None  # streamed upload => UNSIGNED-PAYLOAD
        else:
            raw, signed = b"", b""
        headers = self.headers(method, path, signed, **hk)
        if json_body is not None:
            headers["Content-Type"] = "application/json"
        headers.update(extra or {})
        return client.request(method, path, content=raw if raw else None, headers=headers)

    def send_file(self, client: TestClient, name: str, data: bytes, *, transfer_id: str | None = None, sha: str | None = None):
        tid = transfer_id or str(uuid.uuid4())
        meta = {"transfer_id": tid, "name": name, "size": len(data), "sha256": sha or hashlib.sha256(data).hexdigest()}
        r = self.call(client, "POST", "/v1/transfers", json_body=meta)
        assert r.status_code in (200, 201), r.text
        return tid, r


@pytest.fixture
def settings(tmp_path):
    return Settings(
        data_dir=tmp_path / "data", inbox_dir=tmp_path / "inbox", min_free_bytes=0,
        pairing_wait_seconds=5, pairing_poll_seconds=0.02, advertise_hosts=["192.168.1.50"], pc_name="TESTPC",
    )


@pytest.fixture
def app(settings):
    return create_app(settings, cert_sha256="ab" * 32, admin_allowed_hosts={"testclient"})


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


def pair(client: TestClient, app, phone: FakePhone, approve: bool = True):
    start = client.post("/admin/api/pairing", headers=ADMIN).json()
    import base64 as b64
    import json

    payload = json.loads(b64.urlsafe_b64decode(start["payload"] + "=="))

    def decide():
        time.sleep(0.15)
        (app.state.pairing.approve if approve else app.state.pairing.deny)(start["session_id"])

    t = threading.Thread(target=decide)
    t.start()
    r = client.post("/v1/pair/claim", json={"token": payload["token"], "device_name": phone.name, "public_key": phone.public_b64})
    t.join()
    if r.status_code == 200:
        phone.device_id = r.json()["device_id"]
    return r, payload


@pytest.fixture
def phone(client, app):
    p = FakePhone()
    r, _ = pair(client, app, p)
    assert r.status_code == 200, r.text
    return p
