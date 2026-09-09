import ssl
from datetime import UTC, datetime, timedelta

from app import certificates


def test_bundled_gigachat_certificate_is_verified() -> None:
    status = certificates.inspect_gigachat_certificate(datetime(2026, 9, 9, tzinfo=UTC))

    assert status.state == "ready"
    assert status.expires_at == "2032-02-27T21:04:15Z"
    assert isinstance(certificates.create_gigachat_ssl_context(), ssl.SSLContext)


def test_certificate_expiring_and_expired_states() -> None:
    expiry = datetime(2032, 2, 27, 21, 4, 15, tzinfo=UTC)

    assert certificates.inspect_gigachat_certificate(expiry - timedelta(days=30)).state == "expiring"
    assert certificates.inspect_gigachat_certificate(expiry).state == "expired"


def test_missing_certificate_disables_only_gigachat(monkeypatch) -> None:
    monkeypatch.setattr(certificates, "CERTIFICATE_NAME", "absent.crt")

    status = certificates.inspect_gigachat_certificate()

    assert status.state == "missing"
    assert status.available is False
