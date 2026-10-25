import pytest

from mconn_receiver.config import Settings
from mconn_receiver.database.db import Database
from mconn_receiver.errors import MConnError
from mconn_receiver.pairing.service import Identity, PairingService
from mconn_receiver.util import now_ms


def test_approval_rejects_a_session_that_expired_after_claim(tmp_path):
    db = Database(tmp_path / "mconn.db")
    service = PairingService(
        db,
        Settings(data_dir=tmp_path, inbox_dir=tmp_path / "inbox"),
        Identity(pc_id="pc", pc_name="PC", cert_sha256="ab" * 32, port=8443),
    )
    db.run(
        "INSERT INTO pairing_sessions(session_id, token_hash, created_at, expires_at, pending_device_name, pending_public_key) "
        "VALUES (?,?,?,?,?,?)",
        ("expired", "hash", now_ms() - 2_000, now_ms() - 1_000, "Phone", "public-key"),
    )

    with pytest.raises(MConnError, match="expired") as exc:
        service.approve("expired")

    assert exc.value.status == 403
    assert db.one("SELECT outcome FROM pairing_sessions WHERE session_id='expired'")["outcome"] == "EXPIRED"
