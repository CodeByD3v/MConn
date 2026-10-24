import hashlib
import os
import uuid

from conftest import FakePhone, pair


def inbox_files(settings):
    return sorted(p.name for p in settings.inbox_dir.iterdir() if p.is_file())


def staging_files(settings):
    return list(settings.staging_dir.glob("*"))


def upload(phone, client, tid, data, offset=0):
    return phone.call(client, "PUT", f"/v1/transfers/{tid}/content", content=data, extra={"Upload-Offset": str(offset)})


def test_roundtrip_delivers_identical_bytes(client, phone, settings):
    data = os.urandom(300_000)
    tid, created = phone.send_file(client, "report.zip", data)
    assert created.status_code == 201 and created.json()["bytes_received"] == 0
    r = upload(phone, client, tid, data)
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "COMMITTED" and body["receipt"]["stored_name"] == "report.zip"
    assert (settings.inbox_dir / "report.zip").read_bytes() == data
    assert staging_files(settings) == []
    assert str(settings.inbox_dir) not in r.text  # receipts never leak absolute paths


def test_duplicate_create_after_commit_returns_receipt_without_new_file(client, phone, settings):
    data = b"hello"
    tid, _ = phone.send_file(client, "a.txt", data)
    upload(phone, client, tid, data)
    _, again = phone.send_file(client, "a.txt", data, transfer_id=tid)
    assert again.status_code == 200 and again.json()["state"] == "COMMITTED"
    assert upload(phone, client, tid, data).json()["state"] == "COMMITTED"  # re-PUT is idempotent too
    assert inbox_files(settings) == ["a.txt"]


def test_same_transfer_id_with_different_content_conflicts(client, phone):
    tid, _ = phone.send_file(client, "a.txt", b"one")
    r = phone.call(client, "POST", "/v1/transfers", json_body={
        "transfer_id": tid, "name": "a.txt", "size": 3, "sha256": hashlib.sha256(b"two").hexdigest()})
    assert r.status_code == 409 and r.json()["error"] == "TRANSFER_CONFLICT"


def test_name_collision_gets_suffix_and_never_overwrites(client, phone, settings):
    for payload in (b"first", b"second", b"third"):
        tid, _ = phone.send_file(client, "same.txt", payload)
        upload(phone, client, tid, payload)
    assert inbox_files(settings) == ["same (1).txt", "same (2).txt", "same.txt"]
    assert (settings.inbox_dir / "same.txt").read_bytes() == b"first"


def test_path_traversal_name_is_confined_to_inbox(client, phone, settings):
    tid, _ = phone.send_file(client, "../../evil.txt", b"x")
    upload(phone, client, tid, b"x")
    assert inbox_files(settings) == ["evil.txt"]
    assert not (settings.inbox_dir.parent / "evil.txt").exists()


def test_resume_from_offset(client, phone, settings):
    data = os.urandom(100_000)
    tid, _ = phone.send_file(client, "big.bin", data)
    half = 40_000
    r1 = upload(phone, client, tid, data[:half])
    assert r1.json() == {"transfer_id": tid, "state": "UPLOADING", "bytes_received": half, "max_chunk_bytes": settings.max_chunk_bytes}
    assert phone.call(client, "GET", f"/v1/transfers/{tid}").json()["bytes_received"] == half
    wrong = upload(phone, client, tid, data[half:], offset=0)
    assert wrong.status_code == 409 and wrong.json()["error"] == "OFFSET_MISMATCH" and wrong.json()["bytes_received"] == half
    r2 = upload(phone, client, tid, data[half:], offset=half)
    assert r2.json()["state"] == "COMMITTED"
    assert (settings.inbox_dir / "big.bin").read_bytes() == data


def test_hash_mismatch_commits_nothing_and_allows_retry(client, phone, settings):
    good = b"the real content"
    tid, _ = phone.send_file(client, "x.bin", good)
    r = upload(phone, client, tid, b"corrupted bytes!")  # same length, different bytes
    assert r.status_code == 422 and r.json()["error"] == "HASH_MISMATCH" and r.json()["retryable"] is True
    assert inbox_files(settings) == [] and staging_files(settings) == []
    assert upload(phone, client, tid, good).json()["state"] == "COMMITTED"


def test_zero_byte_file(client, phone, settings):
    tid, _ = phone.send_file(client, "empty.txt", b"")
    headers = phone.headers("PUT", f"/v1/transfers/{tid}/content", None)
    headers["Upload-Offset"] = "0"
    r = client.put(f"/v1/transfers/{tid}/content", headers=headers)
    assert r.status_code == 200 and r.json()["state"] == "COMMITTED"
    assert (settings.inbox_dir / "empty.txt").read_bytes() == b""


def test_size_limit_and_oversize_body(client, phone, settings):
    settings.max_file_bytes = 10
    r = phone.call(client, "POST", "/v1/transfers", json_body={
        "transfer_id": str(uuid.uuid4()), "name": "big", "size": 11, "sha256": "0" * 64})
    assert r.status_code == 413
    tid, _ = phone.send_file(client, "ok.txt", b"12345")
    r = upload(phone, client, tid, b"1234567890")  # more than declared
    assert r.status_code == 400
    assert inbox_files(settings) == []


def test_other_devices_cannot_see_my_transfers(client, app, phone):
    tid, _ = phone.send_file(client, "private.txt", b"secret")
    other = FakePhone("Other")
    r, _ = pair(client, app, other)
    assert r.status_code == 200
    assert other.call(client, "GET", f"/v1/transfers/{tid}").status_code == 404
    assert upload(other, client, tid, b"secret").status_code == 404


def test_inbox_listing(client, phone):
    tid, _ = phone.send_file(client, "a.txt", b"a")
    upload(phone, client, tid, b"a")
    items = phone.call(client, "GET", "/v1/inbox?limit=5").json()["items"]
    assert [i["stored_name"] for i in items] == ["a.txt"]


def test_reconcile_recovers_crash_after_move(app, client, phone, settings):
    """Simulate: file moved into inbox, process died before the DB said COMMITTED."""
    data = b"crash-test"
    tid, _ = phone.send_file(client, "c.txt", data)
    db = app.state.db
    (settings.inbox_dir / "c.txt").write_bytes(data)
    db.run("UPDATE transfers SET final_path=?, stored_name='c.txt', bytes_received=? WHERE transfer_id=?",
           (str(settings.inbox_dir / "c.txt"), len(data), tid))
    app.state.transfers.reconcile()
    assert phone.call(client, "GET", f"/v1/transfers/{tid}").json()["state"] == "COMMITTED"
    assert sorted(p.name for p in settings.inbox_dir.iterdir() if p.is_file()) == ["c.txt"]


def test_reconcile_purges_orphan_parts(app, client, settings):
    orphan = settings.staging_dir / f"{uuid.uuid4()}.part"
    orphan.write_bytes(b"junk")
    app.state.transfers.reconcile()
    assert not orphan.exists()
