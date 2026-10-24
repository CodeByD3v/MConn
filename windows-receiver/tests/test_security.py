import time
import uuid

from conftest import ADMIN, FakePhone


def test_unpaired_device_is_rejected(client):
    stranger = FakePhone()
    stranger.device_id = str(uuid.uuid4())
    r = stranger.call(client, "GET", "/v1/device/status")
    assert r.status_code == 403 and r.json()["error"] == "DEVICE_UNKNOWN"


def test_missing_headers_rejected(client, phone):
    assert client.get("/v1/device/status").status_code == 401
    assert client.post("/v1/transfers", json={}).status_code == 401


def test_bad_signature_rejected(client, phone):
    h = phone.headers("GET", "/v1/device/status", b"")
    h["X-MConn-Signature"] = h["X-MConn-Signature"][:-4] + "AAAA"
    r = client.get("/v1/device/status", headers=h)
    assert r.status_code == 401 and r.json()["error"] == "BAD_SIGNATURE"


def test_signature_binds_path_and_method(client, phone):
    h = phone.headers("GET", "/v1/device/status", b"")
    assert client.get("/v1/inbox", headers=h).status_code == 401  # signed for a different path


def test_signature_binds_body(client, phone):
    h = phone.headers("POST", "/v1/transfers", b'{"a":1}')
    r = client.post("/v1/transfers", content=b'{"a":2}', headers={**h, "Content-Type": "application/json"})
    assert r.status_code == 401


def test_replayed_request_rejected(client, phone):
    h = phone.headers("GET", "/v1/device/status", b"")
    assert client.get("/v1/device/status", headers=h).status_code == 200
    r = client.get("/v1/device/status", headers=h)
    assert r.status_code == 401 and r.json()["error"] == "STALE_REQUEST"


def test_stale_timestamp_rejected(client, phone):
    h = phone.headers("GET", "/v1/device/status", b"", ts=int(time.time()) - 3600)
    r = client.get("/v1/device/status", headers=h)
    assert r.status_code == 401 and r.json()["error"] == "STALE_REQUEST" and r.json()["retryable"] is True


def test_revoked_device_cannot_send(client, phone):
    assert phone.call(client, "GET", "/v1/device/status").status_code == 200
    assert client.post(f"/admin/api/devices/{phone.device_id}/revoke", headers=ADMIN).status_code == 200
    r = phone.call(client, "GET", "/v1/device/status")
    assert r.status_code == 403 and r.json()["error"] == "DEVICE_REVOKED"
    r = phone.call(client, "POST", "/v1/transfers", json_body={
        "transfer_id": str(uuid.uuid4()), "name": "a", "size": 1, "sha256": "0" * 64})
    assert r.status_code == 403


def test_no_docs_or_openapi_exposed(client):
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404
