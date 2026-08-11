"""Admin license generation — key shown once; store hash only."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_admin
from app.entitlement import entitlement_expires_from_issue
from app.models import License
from app.schemas import AdminGenerateLicenseRequest, AdminGenerateLicenseResponse
from app.security import generate_license_key, hash_token

router = APIRouter(prefix="/v1/admin/licenses", tags=["admin"])


@router.post("/generate", response_model=AdminGenerateLicenseResponse, dependencies=[Depends(require_admin)])
def generate(body: AdminGenerateLicenseRequest, db: Session = Depends(get_db)) -> AdminGenerateLicenseResponse:
    plan = body.plan.lower()
    key = generate_license_key(plan)
    issued = datetime.now(UTC)
    expires = entitlement_expires_from_issue(issued)  # always 365 days from issued_at
    prefix = "-".join(key.split("-")[:2])  # EDU-PRO
    row = License(
        key_hash=hash_token(key),
        key_prefix=prefix,
        plan=plan,
        issued_at=issued,
        expires_at=expires,
        status="issued",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return AdminGenerateLicenseResponse(
        license_key=key,
        plan=plan,
        issued_at=issued,
        expires_at=expires,
        license_id=row.id,
    )
