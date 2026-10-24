"""Interface selection. The receiver binds only to loopback, private LAN, and CGNAT (Tailscale) addresses."""
from __future__ import annotations

import ipaddress
import socket

import psutil

_CGNAT = ipaddress.ip_network("100.64.0.0/10")  # Tailscale addresses


def _allowed(ip: ipaddress.IPv4Address) -> bool:
    if ip.is_link_local:
        return False
    return ip.is_loopback or ip.is_private or ip in _CGNAT


def candidate_ips() -> list[str]:
    """Non-loopback private/Tailscale IPv4 addresses on this machine."""
    found: list[str] = []
    for addrs in psutil.net_if_addrs().values():
        for a in addrs:
            if a.family != socket.AF_INET:
                continue
            ip = ipaddress.ip_address(a.address)
            if _allowed(ip) and not ip.is_loopback and a.address not in found:
                found.append(a.address)
    return found


def bind_hosts() -> list[str]:
    return ["127.0.0.1", *candidate_ips()]
