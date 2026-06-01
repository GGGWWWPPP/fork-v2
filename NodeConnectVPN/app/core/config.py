from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

class Settings(BaseSettings):
    PROJECT_NAME: str = "NodeConnectVPN"
    API_V1_STR: str = "/api/v1"
    
    # CORS
    BACKEND_CORS_ORIGINS: List[str] = ["*"]
    
    # Окружение
    ENVIRONMENT: str = "development" # "development" или "production"

    # База данных PostgreSQL (для Production)
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "password"
    POSTGRES_DB: str = "nodeconnect"
    
    # База данных SQLite (для локальной разработки)
    SQLITE_URL: str = "sqlite+aiosqlite:///./nodeconnect.db"

    @property
    def DATABASE_URL(self) -> str:
        """Динамический URL базы данных в зависимости от окружения"""
        if self.ENVIRONMENT == "production":
            return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}/{self.POSTGRES_DB}"
        return self.SQLITE_URL

    # Security
    SECRET_KEY: str = "CHANGE_THIS_SECRET_KEY_IN_PRODUCTION"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)

settings = Settings()
