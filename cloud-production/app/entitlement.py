"""Sign local desktop entitlements (JWS-like JWT with RS256)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from jose import jwt

from app.config import get_settings


def _load_private_pem() -> str:
    path = Path(get_settings().entitlement_private_key_path)
    if not path.is_file():
        raise FileNotFoundError(f"Entitlement private key missing: {path}")
    return path.read_text(encoding="utf-8")


def issue_entitlement(
    *,
    account_id: str,
    school_name: str,
    plan: str,
    email: str,
    expires_at: datetime,
    source: str,
    license_id: str | None = None,
    device_hash: str | None = None,
) -> str:
    """Return a signed entitlement JWT for offline desktop verification."""
    settings = get_settings()
    now = datetime.now(UTC)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    payload: dict[str, Any] = {
        "iss": settings.entitlement_issuer,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "account_id": account_id,
        "email": email,
        "school": school_name,
        "plan": plan.lower(),
        "source": source,  # trial | license
        "license_id": license_id,
        "device_hash": device_hash,
        "typ": "edutrack_entitlement",
    }
    return jwt.encode(payload, _load_private_pem(), algorithm="RS256")


def entitlement_expires_from_issue(issued_at: datetime | None = None) -> datetime:
    """Licenses always expire 365 days from issued_at (VPS authoritative)."""
    settings = get_settings()
    base = issued_at or datetime.now(UTC)
    if base.tzinfo is None:
        base = base.replace(tzinfo=UTC)
    return base + timedelta(days=settings.entitlement_ttl_days)
