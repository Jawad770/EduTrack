"""License activate / verify."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_account
from app.entitlement import issue_entitlement
from app.models import Account, DeviceRegistration, License, School
from app.schemas import (
    ActivateLicenseRequest,
    ActivateLicenseResponse,
    VerifyEntitlementRequest,
    VerifyEntitlementResponse,
)
from app.security import hash_token

router = APIRouter(prefix="/v1/licenses", tags=["licenses"])


@router.post("/activate", response_model=ActivateLicenseResponse)
def activate(
    body: ActivateLicenseRequest,
    account: Account = Depends(get_current_account),
    db: Session = Depends(get_db),
) -> ActivateLicenseResponse:
    key = body.license_key.strip().upper()
    key_h = hash_token(key)
    lic = db.scalar(select(License).where(License.key_hash == key_h))
    if lic is None:
        raise HTTPException(status_code=400, detail="Invalid license key")
    now = datetime.now(UTC)
    exp = lic.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=UTC)
    if lic.status == "revoked":
        raise HTTPException(status_code=400, detail="License revoked")
    if exp < now:
        lic.status = "expired"
        db.commit()
        raise HTTPException(status_code=400, detail="License expired")
    if lic.status == "activated" and lic.account_id and lic.account_id != account.id:
        raise HTTPException(status_code=409, detail="License already activated on another account")

    school = db.scalar(select(School).where(School.account_id == account.id))
    lic.status = "activated"
    lic.activated_at = now
    lic.account_id = account.id
    lic.school_id = school.id if school else None

    if body.device_hash:
        existing_dev = db.scalar(
            select(DeviceRegistration).where(
                DeviceRegistration.account_id == account.id,
                DeviceRegistration.device_hash == body.device_hash,
            )
        )
        if existing_dev is None:
            db.add(
                DeviceRegistration(
                    account_id=account.id,
                    device_hash=body.device_hash,
                    label="desktop",
                )
            )
        else:
            existing_dev.last_seen_at = now


    token = issue_entitlement(
        account_id=account.id,
        school_name=school.name if school else "School",
        plan=lic.plan,
        email=account.email,
        expires_at=exp,
        source="license",
        license_id=lic.id,
        device_hash=body.device_hash,
    )
    db.commit()
    return ActivateLicenseResponse(
        status="activated",
        plan=lic.plan,
        expires_at=exp,
        entitlement=token,
    )


@router.post("/verify", response_model=VerifyEntitlementResponse)
def verify(
    body: VerifyEntitlementRequest,
    account: Account = Depends(get_current_account),
    db: Session = Depends(get_db),
) -> VerifyEntitlementResponse:
    """Periodic online verify — re-issue entitlement if a valid license/trial exists."""
    now = datetime.now(UTC)
    school = db.scalar(select(School).where(School.account_id == account.id))

    lic = db.scalar(
        select(License)
        .where(License.account_id == account.id, License.status == "activated")
        .order_by(License.activated_at.desc())
    )
    if lic is not None:
        exp = lic.expires_at if lic.expires_at.tzinfo else lic.expires_at.replace(tzinfo=UTC)
        if exp >= now:
            token = issue_entitlement(
                account_id=account.id,
                school_name=school.name if school else "School",
                plan=lic.plan,
                email=account.email,
                expires_at=exp,
                source="license",
                license_id=lic.id,
                device_hash=body.device_hash,
            )
            return VerifyEntitlementResponse(
                status="ok",
                plan=lic.plan,
                expires_at=exp,
                entitlement=token,
            )

    from app.models import Trial

    trial = db.scalar(select(Trial).where(Trial.account_id == account.id, Trial.status == "active"))
    if trial is not None:
        exp = trial.expires_at if trial.expires_at.tzinfo else trial.expires_at.replace(tzinfo=UTC)
        if exp >= now:
            token = issue_entitlement(
                account_id=account.id,
                school_name=school.name if school else "School",
                plan="trial",
                email=account.email,
                expires_at=exp,
                source="trial",
                device_hash=body.device_hash,
            )
            return VerifyEntitlementResponse(
                status="ok",
                plan="trial",
                expires_at=exp,
                entitlement=token,
            )
        trial.status = "expired"
        db.commit()

    return VerifyEntitlementResponse(
        status="expired",
        message="No active trial or license. Enter a license key to continue.",
    )
