"""SMTP email sender for OTP / verification."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.config import get_settings

logger = logging.getLogger(__name__)


class EmailNotConfiguredError(RuntimeError):
    pass


def send_email(*, to: str, subject: str, body: str) -> None:
    settings = get_settings()
    if not settings.smtp_host or not settings.smtp_password:
        raise EmailNotConfiguredError(
            "SMTP is not configured. Set SMTP_HOST, SMTP_USER, SMTP_PASSWORD on the VPS."
        )

    msg = EmailMessage()
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)
    logger.info("email_sent to=%s subject=%s", to, subject)


def send_otp_email(to: str, purpose: str, code: str) -> None:
    if purpose == "verify_email":
        subject = "EduTrack — verify your email"
        body = (
            f"Your EduTrack verification code is: {code}\n\n"
            f"This code expires in {get_settings().otp_ttl_minutes} minutes.\n"
            "If you did not create an EduTrack account, ignore this email.\n"
        )
    else:
        subject = "EduTrack — password reset code"
        body = (
            f"Your EduTrack password reset code is: {code}\n\n"
            f"This code expires in {get_settings().otp_ttl_minutes} minutes.\n"
            "If you did not request a reset, ignore this email.\n"
        )
    send_email(to=to, subject=subject, body=body)
