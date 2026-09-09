"""Verification and loading of the application-scoped GigaChat trust anchor."""

from __future__ import annotations

import hashlib
import json
import ssl
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from importlib import resources
from typing import Literal

from cryptography import x509

CertificateState = Literal["ready", "expiring", "expired", "missing", "integrity_failed"]
RESOURCE_PACKAGE = "app.resources.certs"
CERTIFICATE_NAME = "russian_trusted_root_ca_pem.crt"
MANIFEST_NAME = "manifest.json"


@dataclass(frozen=True, slots=True)
class CertificateStatus:
    state: CertificateState
    expires_at: str | None = None

    @property
    def available(self) -> bool:
        return self.state in {"ready", "expiring"}


class CertificateUnavailableError(RuntimeError):
    def __init__(self, state: CertificateState) -> None:
        self.state = state
        super().__init__(f"gigachat_certificate_{state}")


def inspect_gigachat_certificate(now: datetime | None = None) -> CertificateStatus:
    current = now or datetime.now(UTC)
    try:
        root = resources.files(RESOURCE_PACKAGE)
        certificate_bytes = root.joinpath(CERTIFICATE_NAME).read_bytes()
        manifest = json.loads(root.joinpath(MANIFEST_NAME).read_text(encoding="utf-8"))
    except (FileNotFoundError, ModuleNotFoundError):
        return CertificateStatus("missing")
    except (UnicodeError, json.JSONDecodeError, KeyError, TypeError):
        return CertificateStatus("integrity_failed")

    # The official archive publishes the checksum for CRLF-terminated PEM
    # lines without a trailing newline. Git may normalize the packaged text
    # file to LF, so hash that canonical representation while still parsing
    # the untouched packaged bytes below.
    canonical_bytes = b"\r\n".join(certificate_bytes.splitlines())
    digest = hashlib.sha256(canonical_bytes).hexdigest().upper()
    if digest != str(manifest.get("sha256", "")).upper():
        return CertificateStatus("integrity_failed")
    try:
        certificate = x509.load_pem_x509_certificate(certificate_bytes)
        expires = certificate.not_valid_after_utc
    except ValueError:
        return CertificateStatus("integrity_failed")
    expires_at = expires.isoformat().replace("+00:00", "Z")
    if current >= expires:
        return CertificateStatus("expired", expires_at)
    if expires - current <= timedelta(days=30):
        return CertificateStatus("expiring", expires_at)
    return CertificateStatus("ready", expires_at)


def create_gigachat_ssl_context() -> ssl.SSLContext:
    status = inspect_gigachat_certificate()
    if not status.available:
        raise CertificateUnavailableError(status.state)
    certificate = resources.files(RESOURCE_PACKAGE).joinpath(CERTIFICATE_NAME)
    with resources.as_file(certificate) as certificate_path:
        return ssl.create_default_context(cafile=str(certificate_path))
