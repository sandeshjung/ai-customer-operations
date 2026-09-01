from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "AI Customer Operations"
    APP_ENV: str = "development"
    DEBUG: bool = True

    redis_url: str = "redis://localhost:6379/0"

    API_V1_PREFIX: str = "/api/v1"

    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "customer_operations"
    POSTGRES_USER: str = "customer_admin"
    POSTGRES_PASSWORD: str = "customer_admin"

    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION: str = "customer_operations_knowledge"
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"

    LLM_API_KEY: str | None = None
    LLM_MODEL: str = "openai/gpt-oss-20b"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://"
            f"{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}"
            f"/{self.POSTGRES_DB}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
