"""Cloud account / license / trial / OTP models."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    principal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    school = relationship("School", back_populates="account", uselist=False)
    trial = relationship("Trial", back_populates="account", uselist=False)


class School(Base):
    __tablename__ = "schools"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    account = relationship("Account", back_populates="school")


class Trial(Base):
    __tablename__ = "trials"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    account_id: Mapped[str] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    school_id: Mapped[str | None] = mapped_column(ForeignKey("schools.id", ondelete="SET NULL"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)  # active|expired|converted

    account = relationship("Account", back_populates="trial")


class License(Base):
    __tablename__ = "licenses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    key_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    key_prefix: Mapped[str] = mapped_column(String(32), nullable=False)  # EDU-PRO-… shown hint
    plan: Mapped[str] = mapped_column(String(32), nullable=False)  # basic|standard|professional
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="issued", nullable=False)
    # issued | activated | revoked | expired
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    account_id: Mapped[str | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"))
    school_id: Mapped[str | None] = mapped_column(ForeignKey("schools.id", ondelete="SET NULL"))


class Otp(Base):
    __tablename__ = "otps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)  # verify_email|reset_password
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    code_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DeviceRegistration(Base):
    __tablename__ = "device_registrations"
    __table_args__ = (UniqueConstraint("account_id", "device_hash", name="uq_device_account"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    device_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BackupObject(Base):
    __tablename__ = "backup_objects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    school_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    plan: Mapped[str] = mapped_column(String(32), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
