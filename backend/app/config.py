from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    DATABASE_URL: str
    TEST_DATABASE_URL: str | None = None   # if set, integration tests use this DB instead
    REDIS_URL: str
    API_PORT: int = 4000
    ENVIRONMENT: str = "development"
    LOGGING_ENABLED: bool = True       # set False to silence all log output
    LOG_LEVEL: str = "info"
    LOG_RETENTION_HOURS: int = 4       # how many hourly log files to keep
    LOG_DIR: str = "logs"              # directory for rotating log files
    LOG_TO_FILE: bool = True           # set False in CI / tests to skip file output
    LOG_REQUEST_BODY: bool = True      # set False to suppress body logging (PII risk)
    IDEMPOTENCY_TTL_SECONDS: int = 86400      # 24 hours
    SSE_REPLAY_WINDOW_SECONDS: int = 300      # 5-minute replay buffer
    DB_POOL_MIN: int = 2
    DB_POOL_MAX: int = 10

    # Phase 2 only — leave None in Phase 1
    JWT_PUBLIC_KEY: str | None = None

    @field_validator("DATABASE_URL")
    @classmethod
    def must_be_postgres(cls, v: str) -> str:
        if not v.startswith("postgresql"):
            raise ValueError("DATABASE_URL must be a postgresql:// URL")
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
