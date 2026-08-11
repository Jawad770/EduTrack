"""Encrypted backup upload / list (Professional foundation)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_account
from app.models import Account, BackupObject, License
from app.schemas import BackupMetaResponse

router = APIRouter(prefix="/v1/backups", tags=["backups"])


def _require_professional(db: Session, account: Account) -> None:
    lic = db.scalar(
        select(License).where(
            License.account_id == account.id,
            License.status == "activated",
            License.plan == "professional",
        )
    )
    if lic is None:
        raise HTTPException(
            status_code=403,
            detail="Cloud backup requires an active Professional license.",
        )


@router.post("/upload", response_model=BackupMetaResponse)
async def upload_backup(
    file: UploadFile = File(...),
    content_hash: str = Form(...),
    plan: str = Form("professional"),
    account: Account = Depends(get_current_account),
    db: Session = Depends(get_db),
) -> BackupMetaResponse:
    _require_professional(db, account)
    settings = get_settings()
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty backup upload")
    digest = hashlib.sha256(raw).hexdigest()
    if digest.lower() != content_hash.lower():
        raise HTTPException(status_code=400, detail="Content hash mismatch — upload rejected")

    obj_id = str(uuid4())
    dest_dir = Path(settings.backup_storage_dir) / account.id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{obj_id}.bin"
    dest.write_bytes(raw)

    row = BackupObject(
        id=obj_id,
        account_id=account.id,
        content_hash=digest,
        size_bytes=len(raw),
        plan=plan,
        storage_path=str(dest),
        notes="encrypted_blob",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return BackupMetaResponse(
        id=row.id,
        content_hash=row.content_hash,
        size_bytes=row.size_bytes,
        plan=row.plan,
        created_at=row.created_at,
    )


@router.get("", response_model=list[BackupMetaResponse])
def list_backups(
    account: Account = Depends(get_current_account),
    db: Session = Depends(get_db),
) -> list[BackupMetaResponse]:
    _require_professional(db, account)
    rows = db.scalars(
        select(BackupObject)
        .where(BackupObject.account_id == account.id)
        .order_by(BackupObject.created_at.desc())
        .limit(50)
    ).all()
    return [
        BackupMetaResponse(
            id=r.id,
            content_hash=r.content_hash,
            size_bytes=r.size_bytes,
            plan=r.plan,
            created_at=r.created_at,
        )
        for r in rows
    ]
