"""Optional mDNS advertisement (_mconn._tcp). UNVERIFIED on real networks: part of the Phase 0 spike."""
from __future__ import annotations

import logging
import re
import socket

log = logging.getLogger("mconn.discovery")


def start_mdns(pc_id: str, pc_name: str, ips: list[str], port: int):
    try:
        from zeroconf import ServiceInfo, Zeroconf
    except ImportError:
        log.info("zeroconf not installed; mDNS disabled (pip install 'mconn-receiver[mdns]')")
        return None
    if not ips:
        return None
    label = re.sub(r"[^A-Za-z0-9 _-]", "", pc_name)[:40] or "PC"
    info = ServiceInfo(
        "_mconn._tcp.local.",
        f"MConn {label}._mconn._tcp.local.",
        addresses=[socket.inet_aton(ip) for ip in ips],
        port=port,
        properties={"pc_id": pc_id, "v": "1"},
    )
    zc = Zeroconf()
    zc.register_service(info)
    return zc
