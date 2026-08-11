"""Auth: signup, verify email, login, forgot password OTP."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_account
from app.email_smtp import EmailNotConfiguredError, send_otp_email
from app.models import Account, Otp, School
from app.schemas import (
    ForgotRequest,
    LoginRequest,
    MessageResponse,
    ResetPasswordRequest,
    SignupRequest,
    SignupResponse,
    TokenResponse,
    VerifyEmailRequest,
    VerifyOtpRequest,
)
from app.security import (
    create_access_token,
    generate_otp,
    hash_password,
    hash_token,
    verify_password,
)

router = APIRouter(prefix="/v1/auth", tags=["auth"])

GENERIC_OTP = MessageResponse(
    status="ok",
    message="If an account exists for that email, a code has been sent.",
)


def _create_otp(db: Session, *, email: str, purpose: str) -> str:
    settings = get_settings()
    code = generate_otp()
    row = Otp(
        purpose=purpose,
        email=email.lower().strip(),
        code_hash=hash_token(code),
        expires_at=datetime.now(UTC) + timedelta(minutes=settings.otp_ttl_minutes),
    )
    db.add(row)
    db.flush()
    return code


def _verify_otp(db: Session, *, email: str, purpose: str, code: str) -> Otp:
    settings = get_settings()
    email_n = email.lower().strip()
    row = db.scalar(
        select(Otp)
        .where(
            Otp.email == email_n,
            Otp.purpose == purpose,
            Otp.used_at.is_(None),
        )
        .order_by(Otp.created_at.desc())
    )
    if row is None:
        raise HTTPException(status_code=400, detail="Invalid or expired code")
    if row.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
        raise HTTPException(status_code=400, detail="Invalid or expired code")
    if row.attempts >= settings.otp_max_attempts:
        raise HTTPException(status_code=429, detail="Too many attempts")
    row.attempts += 1
    if row.code_hash != hash_token(code.strip()):
        db.flush()
        raise HTTPException(status_code=400, detail="Invalid or expired code")
    row.used_at = datetime.now(UTC)
    db.flush()
    return row


@router.post("/signup", response_model=SignupResponse)
def signup(body: SignupRequest, db: Session = Depends(get_db)) -> SignupResponse:
    email = body.email.lower().strip()
    existing = db.scalar(select(Account).where(Account.email == email))
    if existing:
        # Generic-ish: still return ok-shaped to reduce enumeration slightly,
        # but signup conflicts are useful for UX — use 409.
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    account = Account(
        email=email,
        password_hash=hash_password(body.password),
        principal_name=body.principal_name.strip(),
        email_verified=False,
    )
    db.add(account)
    db.flush()
    school = School(account_id=account.id, name=body.school_name.strip())
    db.add(school)
    code = _create_otp(db, email=email, purpose="verify_email")
    try:
        send_otp_email(email, "verify_email", code)
    except EmailNotConfiguredError as exc:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc
    db.commit()
    return SignupResponse(
        status="pending_verification",
        message="Check your email for a verification code.",
        email=email,
    )


@router.post("/verify-email", response_model=TokenResponse)
def verify_email(body: VerifyEmailRequest, db: Session = Depends(get_db)) -> TokenResponse:
    email = body.email.lower().strip()
    account = db.scalar(select(Account).where(Account.email == email))
    if account is None:
        raise HTTPException(status_code=400, detail="Invalid or expired code")
    _verify_otp(db, email=email, purpose="verify_email", code=body.code)
    account.email_verified = True
    school = db.scalar(select(School).where(School.account_id == account.id))
    token = create_access_token(account.id, {"email": account.email})
    db.commit()
    return TokenResponse(
        access_token=token,
        email=account.email,
        principal_name=account.principal_name,
        school_name=school.name if school else None,
        email_verified=True,
    )


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    email = body.email.lower().strip()
    account = db.scalar(select(Account).where(Account.email == email))
    if account is None or not verify_password(body.password, account.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not account.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")
    school = db.scalar(select(School).where(School.account_id == account.id))
    token = create_access_token(account.id, {"email": account.email})
    return TokenResponse(
        access_token=token,
        email=account.email,
        principal_name=account.principal_name,
        school_name=school.name if school else None,
        email_verified=account.email_verified,
    )


@router.post("/forgot/request-otp", response_model=MessageResponse)
def forgot_request(body: ForgotRequest, db: Session = Depends(get_db)) -> MessageResponse:
    email = body.email.lower().strip()
    account = db.scalar(select(Account).where(Account.email == email))
    if account is None:
        return GENERIC_OTP
    code = _create_otp(db, email=email, purpose="reset_password")
    try:
        send_otp_email(email, "reset_password", code)
    except EmailNotConfiguredError:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail="Email service is temporarily unavailable. Try again later.",
        )
    db.commit()
    return GENERIC_OTP


@router.post("/forgot/verify-otp", response_model=MessageResponse)
def forgot_verify(body: VerifyOtpRequest, db: Session = Depends(get_db)) -> MessageResponse:
    _verify_otp(db, email=body.email, purpose=body.purpose or "reset_password", code=body.code)
    db.commit()
    return MessageResponse(status="ok", message="Code verified. You may reset your password.")


@router.post("/forgot/reset-password", response_model=MessageResponse)
def reset_password(body: ResetPasswordRequest, db: Session = Depends(get_db)) -> MessageResponse:
    email = body.email.lower().strip()
    account = db.scalar(select(Account).where(Account.email == email))
    if account is None:
        raise HTTPException(status_code=400, detail="Invalid or expired code")
    _verify_otp(db, email=email, purpose="reset_password", code=body.code)
    account.password_hash = hash_password(body.new_password)
    db.commit()
    return MessageResponse(status="ok", message="Password updated. You can sign in.")


@router.get("/me", response_model=TokenResponse)
def me(account: Account = Depends(get_current_account), db: Session = Depends(get_db)) -> TokenResponse:
    school = db.scalar(select(School).where(School.account_id == account.id))
    return TokenResponse(
        access_token="",
        email=account.email,
        principal_name=account.principal_name,
        school_name=school.name if school else None,
        email_verified=account.email_verified,
    )
