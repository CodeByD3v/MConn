"""Self-signed receiver certificate. The phone pins its SHA-256 fingerprint (from the pairing QR)."""
from __future__ import annotations

import hashlib
import ipaddress
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID


def fingerprint_of(cert_pem: bytes) -> str:
    cert = x509.load_pem_x509_certificate(cert_pem)
    return hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()


def _certificate_san_hosts(cert_pem: bytes) -> set[str]:
    cert = x509.load_pem_x509_certificate(cert_pem)
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except x509.ExtensionNotFound:
        return set()
    return {
        *(str(value) for value in san.get_values_for_type(x509.IPAddress)),
        *(value.lower() for value in san.get_values_for_type(x509.DNSName)),
    }


def _normalise_host(host: str) -> str:
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        return host.lower()


def ensure_certificate(tls_dir: Path, pc_name: str, hosts: list[str]) -> tuple[Path, Path, str]:
    """Return (cert_path, key_path, sha256_fingerprint_hex), generating them on first run."""
    tls_dir.mkdir(parents=True, exist_ok=True)
    cert_path, key_path = tls_dir / "receiver.crt", tls_dir / "receiver.key"
    if cert_path.exists() and key_path.exists():
        pem = cert_path.read_bytes()
        missing = {_normalise_host(host) for host in hosts} - _certificate_san_hosts(pem)
        if missing:
            values = ", ".join(sorted(missing))
            raise ValueError(
                f"Existing receiver certificate does not contain advertised host(s): {values}. "
                "Rotate the certificate and re-pair devices, or advertise only hosts already in its SAN."
            )
        return cert_path, key_path, fingerprint_of(pem)

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"MConn {pc_name}"[:60])])
    san: list[x509.GeneralName] = [x509.DNSName("localhost")]
    for host in hosts:
        try:
            san.append(x509.IPAddress(ipaddress.ip_address(host)))
        except ValueError:
            # Private-network hostnames (for example a Tailscale DNS name)
            # are validated by OkHttp against a DNS SAN.
            san.append(x509.DNSName(host))
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .sign(key, hashes.SHA256())
    )
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    try:
        os.chmod(key_path, 0o600)
    except OSError:
        pass
    pem = cert.public_bytes(serialization.Encoding.PEM)
    cert_path.write_bytes(pem)
    return cert_path, key_path, fingerprint_of(pem)
