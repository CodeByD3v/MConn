# windows-receiver

FastAPI receiver for MConn. Implements the protocol in `../protocol/transfer-contracts.md`.

## Run (development)

```bash
cd windows-receiver
python -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"                              # add ,mdns for mDNS advertisement
pytest                                               # 45 tests
python main.py                                       # or: mconn-receiver
```

Then open `https://127.0.0.1:8443/admin` (accept the self-signed certificate warning once, this page is local-only), click **Pair new phone**, and scan the QR with the Android app.

## Layout

| Path | Responsibility |
| --- | --- |
| `mconn_receiver/api/` | HTTP routes (`app.py`), request authentication (`auth.py`), local admin UI (`admin.py`) |
| `mconn_receiver/pairing/` | Pairing sessions, device registry, revocation |
| `mconn_receiver/transfer/` | Upload sessions, offsets, hash verification, receipts, crash reconciliation |
| `mconn_receiver/storage/` | Filename sanitising, conflict resolution, atomic commit |
| `mconn_receiver/database/` | SQLite + numbered migrations (mirrors `DATABASE.mmd`) |
| `mconn_receiver/tls.py`, `net.py`, `discovery.py` | Certificate, interface selection, mDNS |

## Configuration

See `config.example.toml`. Defaults: inbox `D:\MConn\Inbox` (or `~/MConn/Inbox`), port 8443, 4 GiB limit.
The receiver binds **only** loopback, private-LAN and Tailscale addresses, never `0.0.0.0`.
