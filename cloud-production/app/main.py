"""EduTrack Cloud API — accounts, trial, licenses, OTP, backups."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import get_engine_dialect_name, init_db
from app.routes import admin, auth, backups, licenses, trial

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("edutrack-cloud")

settings = get_settings()

app = FastAPI(title=settings.app_name, version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(trial.router)
app.include_router(licenses.router)
app.include_router(admin.router)
app.include_router(backups.router)


@app.on_event("startup")
def on_startup() -> None:
    import os

    # Pytest sets CLOUD_TESTING=1 and prepares schema in fixtures.
    if os.environ.get("CLOUD_TESTING") == "1":
        from app.database import verify_database_connection

        verify_database_connection()
        logger.info("database ready (testing) dialect=%s", get_engine_dialect_name())
        return

    # verify_database_connection runs inside init_db — PostgreSQL failures raise here
    init_db()
    logger.info("database ready dialect=%s", get_engine_dialect_name())


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "edutrack-cloud",
        "database": get_engine_dialect_name(),
    }
