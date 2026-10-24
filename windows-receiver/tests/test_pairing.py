import base64
import json

from conftest import ADMIN, FakePhone, pair


def test_pairing_flow_and_status(client, app):
    phone = FakePhone()
    r, payload = pair(client, app, phone)
    assert r.status_code == 200
    assert r.json()["pc_name"] == "TESTPC"
    assert payload["cert_sha256"] == "ab" * 32 and payload["hosts"] == ["192.168.1.50"] and payload["v"] == 1
    s = phone.call(client, "GET", "/v1/device/status")
    assert s.status_code == 200 and s.json()["device_status"] == "ACTIVE"


def test_token_is_single_use(client, app):
    start = client.post("/admin/api/pairing", headers=ADMIN).json()
    token = json.loads(base64.urlsafe_b64decode(start["payload"] + "=="))["token"]
    a = FakePhone()
    import threading
    import time
    threading.Thread(target=lambda: (time.sleep(0.15), app.state.pairing.approve(start["session_id"]))).start()
    assert client.post("/v1/pair/claim", json={"token": token, "device_name": "A", "public_key": a.public_b64}).status_code == 200
    again = client.post("/v1/pair/claim", json={"token": token, "device_name": "B", "public_key": FakePhone().public_b64})
    assert again.status_code == 403 and again.json()["error"] == "PAIRING_INVALID"


def test_denied_pairing(client, app):
    r, _ = pair(client, app, FakePhone(), approve=False)
    assert r.status_code == 403 and r.json()["error"] == "PAIRING_DENIED"


def test_bad_token_and_bad_key(client):
    r = client.post("/v1/pair/claim", json={"token": "nope", "device_name": "x", "public_key": FakePhone().public_b64})
    assert r.status_code == 403
    r = client.post("/v1/pair/claim", json={"token": "nope", "device_name": "x", "public_key": "###"})
    assert r.status_code == 400


def test_admin_is_loopback_and_header_protected(settings):
    from fastapi.testclient import TestClient

    from mconn_receiver.api.app import create_app
    app = create_app(settings)  # default allow-list = loopback only; TestClient host is "testclient"
    with TestClient(app) as c:
        assert c.post("/admin/api/pairing", headers=ADMIN).status_code == 403


def test_admin_requires_custom_header(client):
    assert client.post("/admin/api/pairing").status_code == 403
