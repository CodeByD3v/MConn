# MConn transfer contracts

This is the wire-contract source of truth for MConn v1's phone-to-PC transfer path. All routes use HTTPS.
JSON uses UTF-8, and binary upload content is sent as `application/octet-stream`.
The phone never supplies a destination path, and receipts never expose one.

Direct retrieval from an authorized external source and provider adapters are planned extensions. They require an additive, versioned contract before implementation; no current endpoint accepts provider credentials, conversation identifiers, or arbitrary source references.

## 1. Transport security

The receiver uses a self-signed TLS certificate. Its SHA-256 fingerprint and
the receiver's usable hosts appear in the pairing payload. The phone must:

1. trust only the certificate whose DER SHA-256 matches `cert_sha256`;
2. use normal TLS hostname verification; and
3. connect only to a host represented in that certificate's Subject Alternative
   Name (an IP address is represented by an IP SAN).

The receiver must include each host it advertises in the certificate SAN before
it creates pairing payloads. Certificate validation must never be disabled.

## 2. Request authentication

All `/v1` endpoints except `POST /v1/pair/claim` require these headers:

| Header | Value |
| --- | --- |
| `X-MConn-Device` | Registered `device_id` |
| `X-MConn-Timestamp` | Unix seconds |
| `X-MConn-Nonce` | Unique random 128-bit base64url value |
| `X-MConn-Signature` | base64url DER ECDSA P-256 / SHA-256 signature |

The signed UTF-8 byte string is exactly:

```text
METHOD\nPATH_WITH_OPTIONAL_QUERY\nTIMESTAMP\nNONCE\nBODY_SHA256
```

`METHOD` is upper-case. `BODY_SHA256` is the lower-case hexadecimal SHA-256 of
the exact request body, except a streamed `PUT` upload uses the literal
`UNSIGNED-PAYLOAD`. The receiver rejects timestamps outside five minutes and
nonces already used within that window.

## 3. Pairing

### Pairing payload

The receiver encodes this JSON object with base64url, without padding:

```json
{
  "v": 1,
  "pc_id": "receiver UUID",
  "pc_name": "display name",
  "hosts": ["192.168.1.50"],
  "port": 8443,
  "cert_sha256": "lowercase SHA-256 of certificate DER",
  "token": "single-use token",
  "exp": 1700000300
}
```

`token` is single-use and expires at the Unix-second value `exp`.

### `POST /v1/pair/claim`

Unauthenticated request:

```json
{
  "token": "single-use token",
  "device_name": "Pixel 8",
  "public_key": "base64 DER SubjectPublicKeyInfo P-256 key"
}
```

The receiver waits for explicit PC approval. On success it responds `200`:

```json
{"device_id":"device UUID","pc_id":"receiver UUID","pc_name":"display name"}
```

An invalid, expired, or used token returns `403 PAIRING_INVALID`; denial returns
`403 PAIRING_DENIED`.

## 4. Device and transfer routes

### `GET /v1/device/status`

Returns `200`:

```json
{"pc_id":"receiver UUID","device_status":"ACTIVE","accepting":true}
```

### `POST /v1/transfers`

Request:

```json
{
  "transfer_id": "UUIDv4",
  "name": "report.zip",
  "size": 12345678,
  "sha256": "64 lowercase hexadecimal characters",
  "mime": "application/zip"
}
```

`mime` is optional. A new transfer returns `201`; an existing transfer with the
same device, size, and hash returns `200`. Both return:

```json
{
  "transfer_id":"UUIDv4",
  "state":"UPLOADING",
  "bytes_received":0,
  "max_chunk_bytes":8388608
}
```

For a committed ID, `state` is `COMMITTED` and the response also contains
`receipt`. Reuse of an ID with a different device, size, or hash returns
`409 TRANSFER_CONFLICT`.

### `PUT /v1/transfers/{transfer_id}/content`

Send `Upload-Offset` as a non-negative decimal byte offset. The body contains
bytes starting at that offset. If it differs from the receiver's persisted
offset, the response is `409 OFFSET_MISMATCH` with `bytes_received` containing
the correct offset. A partial upload returns the transfer view above. When the
received byte count equals the declared size, the receiver verifies the full
SHA-256, atomically commits the file, and returns the committed view.

### `GET /v1/transfers/{transfer_id}`

Returns the caller's transfer view. A device cannot read another device's
transfer; unknown or unowned IDs return `404 TRANSFER_NOT_FOUND`.

### `GET /v1/inbox?limit={n}`

Returns the caller's committed receipts, newest first:

```json
{"items":[{"transfer_id":"UUIDv4","state":"COMMITTED","stored_name":"report.zip","size":12345678,"sha256":"...","committed_at":"2026-10-24T10:15:30Z"}]}
```

`limit` is clamped to 1 through 200.

## 5. Receipt and errors

A receipt is:

```json
{
  "transfer_id": "UUIDv4",
  "state": "COMMITTED",
  "stored_name": "report (1).zip",
  "size": 12345678,
  "sha256": "64 lowercase hexadecimal characters",
  "committed_at": "2026-10-24T10:15:30Z"
}
```

Errors have this shape:

```json
{"error":"CODE","message":"Human-readable message","retryable":true}
```

Relevant codes are `INVALID_REQUEST`, `BAD_SIGNATURE`, `STALE_REQUEST`,
`DEVICE_UNKNOWN`, `DEVICE_REVOKED`, `PAIRING_INVALID`, `PAIRING_DENIED`,
`TRANSFER_NOT_FOUND`, `TRANSFER_CONFLICT`, `OFFSET_MISMATCH`,
`FILE_TOO_LARGE`, `HASH_MISMATCH`, `INSUFFICIENT_STORAGE`, and `NOT_ACCEPTING`.

JSON request bodies for `POST /v1/pair/claim` and `POST /v1/transfers` are
limited to 16 KiB, including chunked requests without a `Content-Length`
header. A larger body returns `413 REQUEST_TOO_LARGE` with `retryable: false`.

## 6. Commit guarantees

The receiver streams content to a receiver-controlled staging file, verifies
declared size and SHA-256, sanitises the untrusted filename, allocates a numeric
conflict suffix when needed, then moves the staging file with `os.replace` on
the same volume. It records the committed receipt durably and returns the same
receipt for every later use of that transfer ID. Existing inbox files are never
overwritten.
