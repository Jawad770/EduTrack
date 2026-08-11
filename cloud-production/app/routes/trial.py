"""Trial start (one per account)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_account
from app.entitlement import issue_entitlement
from app.models import Account, DeviceRegistration, School, Trial
from app.schemas import TrialStartRequest, TrialStartResponse

router = APIRouter(prefix="/v1/trial", tags=["trial"])


@router.post("/start", response_model=TrialStartResponse)
def start_trial(
    body: TrialStartRequest,
    account: Account = Depends(get_current_account),
    db: Session = Depends(get_db),
) -> TrialStartResponse:
    if not account.email_verified:
        raise HTTPException(status_code=403, detail="Verify your email before starting a trial")

    existing = db.scalar(select(Trial).where(Trial.account_id == account.id))
    if existing is not None:
        raise HTTPException(status_code=409, detail="A trial was already used for this account")

    settings = get_settings()
    now = datetime.now(UTC)
    expires = now + timedelta(days=settings.trial_days)
    school = db.scalar(select(School).where(School.account_id == account.id))

    trial = Trial(
        account_id=account.id,
        school_id=school.id if school else None,
        started_at=now,
        expires_at=expires,
        status="active",
    )
    db.add(trial)

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

    token = issue_entitlement(
        account_id=account.id,
        school_name=school.name if school else "School",
        plan="trial",
        email=account.email,
        expires_at=expires,
        source="trial",
        device_hash=body.device_hash,
    )
    db.commit()
    return TrialStartResponse(
        status="active",
        plan="trial",
        started_at=now,
        expires_at=expires,
        entitlement=token,
    )
