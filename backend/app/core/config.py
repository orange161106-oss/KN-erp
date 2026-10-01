"""Environment configuration shared by the application and Alembic."""

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def parse_database_url(value: str) -> URL:
    try:
        url = make_url(value)
    except ArgumentError:
        raise ValueError("Use a valid PostgreSQL connection URL") from None
    if url.drivername not in {"postgresql", "postgresql+psycopg"}:
        raise ValueError("Use PostgreSQL with the psycopg driver")
    if not url.host or not url.database or not url.username:
        raise ValueError("The PostgreSQL URL requires a host, database and username")
    # All connections use Psycopg 3, including plain postgresql:// URLs.
    return url.set(drivername="postgresql+psycopg")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        hide_input_in_errors=True,
    )

    app_name: str = Field(default="KN Consumable ERP", min_length=1)
    app_env: Literal["local", "test", "staging", "production"] = "local"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    database_url: SecretStr
    db_connect_timeout_seconds: int = Field(default=5, ge=1, le=60)
    # Schema-only Alembic operations do not need the application's signing key.
    auth_secret_key: SecretStr | None = None
    auth_access_token_expire_minutes: int = Field(default=15, ge=1, le=60)
    auth_token_issuer: str = Field(default="kn-consumable-erp", min_length=1)
    auth_token_audience: str = Field(default="kn-consumable-web", min_length=1)

    @field_validator("auth_secret_key")
    @classmethod
    def validate_auth_secret(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None:
            secret = value.get_secret_value()
            if len(secret.encode("utf-8")) < 32 or not secret.strip():
                raise ValueError("Use an operator-generated signing secret of at least 32 UTF-8 bytes")
        return value

    def signing_key(self) -> str:
        if self.auth_secret_key is None:
            raise RuntimeError("Invalid backend settings: auth_secret_key")
        return self.auth_secret_key.get_secret_value()

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr) -> SecretStr:
        parse_database_url(value.get_secret_value())
        return value

    @property
    def sqlalchemy_url(self) -> URL:
        return parse_database_url(self.database_url.get_secret_value())


def load_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        fields = sorted({str(error["loc"][0]) for error in exc.errors()})
        raise RuntimeError("Invalid backend settings: " + ", ".join(fields)) from None
