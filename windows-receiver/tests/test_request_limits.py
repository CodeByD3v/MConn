import asyncio

import pytest
from starlette.requests import Request

from mconn_receiver.api.app import MAX_JSON_BODY_BYTES, read_json_body
from mconn_receiver.errors import MConnError


def request_with_body(body: bytes, headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    headers = headers or []
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request({"type": "http", "method": "POST", "path": "/v1/pair/claim", "headers": headers}, receive)


def test_json_reader_rejects_oversize_content_length_before_reading():
    request = request_with_body(b"", [(b"content-length", str(MAX_JSON_BODY_BYTES + 1).encode())])

    with pytest.raises(MConnError, match="exceeds 16 KiB") as exc:
        asyncio.run(read_json_body(request))

    assert exc.value.status == 413 and exc.value.code == "REQUEST_TOO_LARGE"


def test_json_reader_rejects_oversize_chunked_body():
    request = request_with_body(b"x" * (MAX_JSON_BODY_BYTES + 1))

    with pytest.raises(MConnError, match="exceeds 16 KiB"):
        asyncio.run(read_json_body(request))


def test_json_reader_accepts_small_body():
    assert asyncio.run(read_json_body(request_with_body(b'{"ok":true}'))) == b'{"ok":true}'
