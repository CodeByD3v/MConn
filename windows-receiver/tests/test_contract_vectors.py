"""Cross-platform contract vectors: the Android SigningTest asserts the SAME strings."""
from mconn_receiver.api.auth import UNSIGNED_PAYLOAD, body_hash, canonical_string

EMPTY = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_empty_body_hash():
    assert body_hash(b"") == EMPTY


def test_canonical_string_vector():
    got = canonical_string("get", "/v1/inbox?limit=5", "1700000000", "abc_DEF-123", EMPTY).decode()
    assert got == f"GET\n/v1/inbox?limit=5\n1700000000\nabc_DEF-123\n{EMPTY}"


def test_streamed_marker():
    got = canonical_string("PUT", "/v1/transfers/x/content", "1", "n", UNSIGNED_PAYLOAD).decode()
    assert got == "PUT\n/v1/transfers/x/content\n1\nn\nUNSIGNED-PAYLOAD"
