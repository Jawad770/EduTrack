"""Cloud service configuration."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT = Path(__file__).resolve().parent.parent


def _default_sqlite_url() -> str:
    """Local-dev default only — production must set DATABASE_URL to PostgreSQL."""
    return f"sqlite:///{(_ROOT / 'cloud_accounts.db').as_posix()}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "EduTrack Cloud"
    # Local default: SQLite. Production: set DATABASE_URL=postgresql+psycopg2://…
    # There is no automatic fallback from PostgreSQL to SQLite.
    database_url: str = _default_sqlite_url()
    # When true, fail startup if DATABASE_URL is still the SQLite default (VPS guard).
    require_postgres: bool = False

    jwt_secret_key: str = "change-me-cloud-jwt-secret-long-random"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7
    admin_api_key: str = "change-me-admin-api-key"

    entitlement_private_key_path: Path = _ROOT / "keys" / "entitlement_private.pem"
    entitlement_issuer: str = "onairo-edutrack"
    entitlement_ttl_days: int = 365

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = "edutrack@onairosolutions.com"
    smtp_password: str = ""
    smtp_from: str = "edutrack@onairosolutions.com"
    smtp_use_tls: bool = True

    trial_days: int = 14
    backup_storage_dir: Path = _ROOT / "backup_blobs"
    cors_origins: list[str] = ["*"]
    otp_ttl_minutes: int = 15
    otp_max_attempts: int = 5

    def assert_production_database(self) -> None:
        """Optional VPS guard: REQUIRE_POSTGRES=true refuses SQLite."""
        if not self.require_postgres:
            return
        url = (self.database_url or "").strip()
        if not url.startswith("postgresql"):
            raise RuntimeError(
                "REQUIRE_POSTGRES=true but DATABASE_URL is not a PostgreSQL URL. "
                "Set DATABASE_URL=postgresql+psycopg2://USER:PASSWORD@HOST:5432/DBNAME"
            )


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.backup_storage_dir.mkdir(parents=True, exist_ok=True)
    s.assert_production_database()
    return s
