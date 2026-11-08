from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Параметры сервера бизнес-логики. Секреты передаются только через переменные окружения (.env)."""

    PROJECT_NAME: str = "Сервер бизнес-логики сегментации клиентов"
    VERSION: str = "2.0.0"
    API_V1_STR: str = "/api/v1"

    POSTGRES_SERVER: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str = "loyalty_db"
    POSTGRES_SSL: bool = True

    AI_SERVICE_URL: str = "https://ai_service:8001"
    AI_TIMEOUT_SECONDS: float = 300.0
    TLS_CA_FILE: str = "/certs/ca.crt"

    JWT_SECRET_KEY: str = Field(..., min_length=32)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    LOGIN_MAX_FAILURES: int = 5
    LOGIN_LOCK_MINUTES: int = 5

    PII_ENCRYPTION_KEY: str = Field(..., description="Ключ AES-256 в base64 для шифрования ПДн")
    PII_HMAC_KEY: str = Field(..., description="Ключ HMAC-SHA-256 в base64 для хеш-индексов ПДн")
    BACKUP_ENCRYPTION_KEY: str = Field(..., description="Ключ AES-256 в base64 для шифрования резервных копий")
    BACKUP_DIR: str = "/backups"

    CORS_ORIGINS: str = "https://localhost:8443"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@"
            f"{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


settings = Settings()
