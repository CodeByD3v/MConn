import pytest
from cryptography import x509

from mconn_receiver.tls import ensure_certificate


def test_certificate_covers_advertised_ip_and_dns_hosts(tmp_path):
    cert, _, _ = ensure_certificate(tmp_path, "Test PC", ["192.168.1.50", "test-pc.tailnet.ts.net"])
    loaded = x509.load_pem_x509_certificate(cert.read_bytes())
    san = loaded.extensions.get_extension_for_class(x509.SubjectAlternativeName).value

    assert str(san.get_values_for_type(x509.IPAddress)[0]) == "192.168.1.50"
    assert "test-pc.tailnet.ts.net" in san.get_values_for_type(x509.DNSName)


def test_existing_certificate_cannot_advertise_uncovered_host(tmp_path):
    ensure_certificate(tmp_path, "Test PC", ["192.168.1.50"])

    with pytest.raises(ValueError, match="does not contain advertised host"):
        ensure_certificate(tmp_path, "Test PC", ["192.168.1.51"])
