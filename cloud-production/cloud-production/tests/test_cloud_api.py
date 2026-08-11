"""Pytest suite for EduTrack Cloud (SQLite by default).

Set DATABASE_URL=postgresql+psycopg2://… to run the same suite against PostgreSQL 16.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# Force a disposable SQLite DB before importing the app (unless caller set PG URL)
_TEST_DB = Path(__file__).resolve().parent / "_pytest_cloud.db"
if not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB.as_posix()}"
os.environ["JWT_SECRET_KEY"] = "pytest-cloud-jwt-secret-key-32chars"
os.environ["ADMIN_API_KEY"] = "pytest-admin-key"
os.environ["REQUIRE_POSTGRES"] = "false"
os.environ["CLOUD_TESTING"] = "1"

# Ensure entitlement key exists for trial/activate
_KEYS = Path(__file__).resolve().parent.parent / "keys"
_PRIV = _KEYS / "entitlement_private.pem"
if not _PRIV.is_file():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    _KEYS.mkdir(parents=True, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    _PRIV.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    (_KEYS / "entitlement_public.pem").write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )

os.environ["ENTITLEMENT_PRIVATE_KEY_PATH"] = str(_PRIV)

from app.config import get_settings  # noqa: E402
from app.database import Base, engine, init_db, verify_database_connection  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _schema():
    get_settings.cache_clear()
    if _TEST_DB.exists() and os.environ["DATABASE_URL"].startswith("sqlite"):
        _TEST_DB.unlink(missing_ok=True)
        for suffix in ("-wal", "-shm"):
            Path(str(_TEST_DB) + suffix).unlink(missing_ok=True)
    # Re-bind: engine already created at import — for sqlite file we recreate tables
    Base.metadata.drop_all(bind=engine)
    init_db(ensure_schema=True)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client():
    return TestClient(app)


def test_health(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["database"] in {"sqlite", "postgresql"}


def test_verify_connection_ok():
    verify_database_connection()


def test_require_postgres_guard(monkeypatch):
    from app import config as config_mod

    monkeypatch.setenv("REQUIRE_POSTGRES", "true")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./should_fail.db")
    config_mod.get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="REQUIRE_POSTGRES"):
        config_mod.get_settings()
    monkeypatch.setenv("REQUIRE_POSTGRES", "false")
    config_mod.get_settings.cache_clear()


def test_admin_generate_license_365_days(client: TestClient):
    r = client.post(
        "/v1/admin/licenses/generate",
        headers={"X-Admin-Key": "pytest-admin-key"},
        json={"plan": "professional"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["license_key"].startswith("EDU-PRO-")
    issued = datetime.fromisoformat(data["issued_at"].replace("Z", "+00:00"))
    expires = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
    delta = expires - issued
    assert timedelta(days=364) <= delta <= timedelta(days=366)


def test_signup_verify_login_trial_activate(client: TestClient):
    email = "principal@example.com"
    password = "SecurePass123"

    with patch("app.routes.auth.send_otp_email") as send_mail:
        # Capture OTP by hashing reverse — read from DB instead
        r = client.post(
            "/v1/auth/signup",
            json={
                "email": email,
                "password": password,
                "principal_name": "Test Principal",
                "school_name": "Test School",
            },
        )
        assert r.status_code == 200, r.text
        assert send_mail.called

    from app.database import SessionLocal
    from app.models import Otp
    from app.security import hash_token
    from sqlalchemy import select

    # Inject a known OTP for verify
    code = "123456"
    db = SessionLocal()
    try:
        row = db.scalar(select(Otp).where(Otp.email == email).order_by(Otp.created_at.desc()))
        assert row is not None
        row.code_hash = hash_token(code)
        row.expires_at = datetime.now(UTC) + timedelta(minutes=15)
        row.used_at = None
        row.attempts = 0
        db.commit()
    finally:
        db.close()

    r = client.post("/v1/auth/verify-email", json={"email": email, "code": code})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    assert token

    r = client.post("/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    token = r.json()["access_token"]

    r = client.post(
        "/v1/trial/start",
        headers={"Authorization": f"Bearer {token}"},
        json={"device_hash": "device-test-1"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["plan"] == "trial"
    assert r.json()["entitlement"]

    # Second trial blocked
    r2 = client.post(
        "/v1/trial/start",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert r2.status_code == 409

    # Generate + activate a license on a fresh account path: use verify
    gen = client.post(
        "/v1/admin/licenses/generate",
        headers={"X-Admin-Key": "pytest-admin-key"},
        json={"plan": "standard"},
    )
    key = gen.json()["license_key"]
    act = client.post(
        "/v1/licenses/activate",
        headers={"Authorization": f"Bearer {token}"},
        json={"license_key": key, "device_hash": "device-test-1"},
    )
    assert act.status_code == 200, act.text
    assert act.json()["plan"] == "standard"

    ver = client.post(
        "/v1/licenses/verify",
        headers={"Authorization": f"Bearer {token}"},
        json={"device_hash": "device-test-1"},
    )
    assert ver.status_code == 200
    assert ver.json()["status"] == "ok"
    assert ver.json()["entitlement"]


def test_backup_metadata_requires_professional(client: TestClient):
    # Login as existing account from previous test if same DB — create dedicated user
    email = "backup@example.com"
    password = "SecurePass123"
    with patch("app.routes.auth.send_otp_email"):
        client.post(
            "/v1/auth/signup",
            json={
                "email": email,
                "password": password,
                "principal_name": "Backup User",
                "school_name": "Backup School",
            },
        )
    from app.database import SessionLocal
    from app.models import Account, Otp
    from app.security import hash_token
    from sqlalchemy import select

    db = SessionLocal()
    try:
        acct = db.scalar(select(Account).where(Account.email == email))
        acct.email_verified = True
        row = db.scalar(select(Otp).where(Otp.email == email).order_by(Otp.created_at.desc()))
        if row:
            row.used_at = datetime.now(UTC)
        db.commit()
    finally:
        db.close()

    login = client.post("/v1/auth/login", json={"email": email, "password": password})
    token = login.json()["access_token"]

    listed = client.get("/v1/backups", headers={"Authorization": f"Bearer {token}"})
    assert listed.status_code == 403

    # Activate professional and upload
    gen = client.post(
        "/v1/admin/licenses/generate",
        headers={"X-Admin-Key": "pytest-admin-key"},
        json={"plan": "professional"},
    )
    key = gen.json()["license_key"]
    client.post(
        "/v1/licenses/activate",
        headers={"Authorization": f"Bearer {token}"},
        json={"license_key": key},
    )

    blob = b"encrypted-fake-backup-bytes"
    import hashlib

    digest = hashlib.sha256(blob).hexdigest()
    up = client.post(
        "/v1/backups/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("b.bin", blob, "application/octet-stream")},
        data={"content_hash": digest, "plan": "professional"},
    )
    assert up.status_code == 200, up.text
    assert up.json()["content_hash"] == digest

    listed = client.get("/v1/backups", headers={"Authorization": f"Bearer {token}"})
    assert listed.status_code == 200
    assert len(listed.json()) >= 1
