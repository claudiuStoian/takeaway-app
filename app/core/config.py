from enum import StrEnum
from typing import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

DEV_DB_PASSWORD = 'takeaway-dev-password'
DEV_JWT_SECRET_KEY = 'dev-only-jwt-secret-change-me-before-production'
# RFC 7518 §3.2: an HS256 key must be at least 256 bits.
JWT_SECRET_MIN_LENGTH = 32


class Environment(StrEnum):
    DEVELOPMENT = 'development'
    TEST = 'test'
    PRODUCTION = 'production'


class AppSettings(BaseSettings):
    # Validation errors would otherwise echo the secrets into startup logs.
    model_config = SettingsConfigDict(frozen=True, hide_input_in_errors=True)

    environment: Environment = Environment.DEVELOPMENT

    db_host: str = 'localhost'
    db_port: int = 5432
    db_name: str = 'takeaway'
    db_user: str = 'takeaway'
    db_password: str = DEV_DB_PASSWORD

    jwt_secret_key: str = DEV_JWT_SECRET_KEY

    @property
    def database_url(self) -> URL:
        # Built from parts so a password with '@', ':' or '/' isn't misparsed.
        return URL.create(
            'postgresql+psycopg',
            username=self.db_user,
            password=self.db_password,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )

    @model_validator(mode='after')
    def refuse_dev_secrets_in_production(self) -> Self:
        if self.environment != Environment.PRODUCTION:
            return self
        if self.jwt_secret_key == DEV_JWT_SECRET_KEY or self.db_password == DEV_DB_PASSWORD:
            raise ValueError('Development secrets must be replaced when ENVIRONMENT=production.')
        if len(self.jwt_secret_key.encode()) < JWT_SECRET_MIN_LENGTH:
            raise ValueError(
                f'JWT_SECRET_KEY must be at least {JWT_SECRET_MIN_LENGTH} bytes '
                'when ENVIRONMENT=production.'
            )
        return self


settings = AppSettings()
