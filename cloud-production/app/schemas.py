"""Pydantic schemas for cloud API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    principal_name: str = Field(min_length=2, max_length=255)
    school_name: str = Field(min_length=2, max_length=255)


class SignupResponse(BaseModel):
    status: str
    message: str
    email: str


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=4, max_length=12)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    email: str
    principal_name: str
    school_name: str | None = None
    email_verified: bool


class ForgotRequest(BaseModel):
    email: EmailStr


class VerifyOtpRequest(BaseModel):
    email: EmailStr
    code: str
    purpose: str = "reset_password"


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    code: str
    new_password: str = Field(min_length=8, max_length=128)


class MessageResponse(BaseModel):
    status: str
    message: str


class TrialStartRequest(BaseModel):
    device_hash: str | None = None


class TrialStartResponse(BaseModel):
    status: str
    plan: str = "trial"
    started_at: datetime
    expires_at: datetime
    entitlement: str


class ActivateLicenseRequest(BaseModel):
    license_key: str
    device_hash: str | None = None


class ActivateLicenseResponse(BaseModel):
    status: str
    plan: str
    expires_at: datetime
    entitlement: str


class VerifyEntitlementRequest(BaseModel):
    entitlement: str | None = None
    device_hash: str | None = None


class VerifyEntitlementResponse(BaseModel):
    status: str
    plan: str | None = None
    expires_at: datetime | None = None
    entitlement: str | None = None
    message: str | None = None


class AdminGenerateLicenseRequest(BaseModel):
    plan: str = Field(pattern="^(basic|standard|professional)$")
    note: str | None = None


class AdminGenerateLicenseResponse(BaseModel):
    license_key: str
    plan: str
    issued_at: datetime
    expires_at: datetime
    license_id: str


class BackupMetaResponse(BaseModel):
    id: str
    content_hash: str
    size_bytes: int
    plan: str
    created_at: datetime
