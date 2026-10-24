"""Entry point: `mconn-receiver` or `python main.py`."""
from __future__ import annotations

import asyncio
import logging
import os
import socket
from logging.handlers import RotatingFileHandler
from pathlib import Path

import uvicorn

from .api.app import create_app
from .config import load_settings
from .discovery import start_mdns
from .net import bind_hosts, candidate_ips
from .tls import ensure_certificate

log = logging.getLogger("mconn")


def configure_logging(data_dir: Path) -> None:
    """Send receiver logs to a bounded file suitable for Task Scheduler."""
    log_dir = data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(log_dir / "receiver.log", maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[handler, logging.StreamHandler()],
    )


def _listen_sockets(hosts: list[str], port: int) -> list[socket.socket]:
    socks = []
    for host in hosts:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if os.name != "nt":  # on Windows SO_REUSEADDR would let another process share the port
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, port))
        s.listen(100)
        s.set_inheritable(True)
        socks.append(s)
    return socks


def main() -> None:
    settings = load_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    configure_logging(settings.data_dir)
    advertised_hosts = settings.advertise_hosts or candidate_ips()
    # Pairing payloads may contain only names represented in the certificate's
    # SAN; Android retains normal hostname validation in addition to pinning.
    settings.advertise_hosts = advertised_hosts
    cert, key, fingerprint = ensure_certificate(settings.tls_dir, settings.pc_name, advertised_hosts)
    app = create_app(settings, cert_sha256=fingerprint)

    hosts = settings.bind_hosts or bind_hosts()  # private interfaces only; never 0.0.0.0
    socks = _listen_sockets(hosts, settings.port)
    zc = start_mdns(app.state.identity.pc_id, settings.pc_name, app.state.identity.hosts, settings.port)

    log.info("Inbox: %s", settings.inbox_dir)
    log.info("Listening on %s port %d", ", ".join(hosts), settings.port)
    log.info("Pair a phone: open https://127.0.0.1:%d/admin (accept the self-signed certificate warning)", settings.port)
    server = uvicorn.Server(uvicorn.Config(app, ssl_certfile=str(cert), ssl_keyfile=str(key), log_level="info"))
    try:
        asyncio.run(server.serve(sockets=socks))
    finally:
        if zc:
            zc.close()


if __name__ == "__main__":
    main()
