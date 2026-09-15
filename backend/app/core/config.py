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
    LLM_MODEL: str = "llama-3.1-8b-instant"

    OTEL_ENABLED: bool = True
    OTEL_SERVICE_NAME: str = "ai-customer-operations"
    # Default points at the local Jaeger container from docker-compose.
    # Swap to a Langfuse OTLP endpoint (+ OTEL_EXPORTER_OTLP_HEADERS for
    # auth) without touching any instrumentation code.
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://localhost:4318"
    OTEL_EXPORTER_OTLP_HEADERS: str | None = None
    JAEGER_UI_URL: str = "http://localhost:16686"

    NOTIFICATION_BACKEND: str = "log"

    # Only needed if you uncomment the Mailjet demo call in
    # notification_service.send_notification() — see that file.
    MAILJET_API_KEY: str | None = None
    MAILJET_API_SECRET: str | None = None
    MAILJET_SENDER_EMAIL: str | None = None
    MAILJET_SENDER_NAME: str = "Customer Support"

    ADMIN_API_KEY: str | None = None

    RATE_LIMIT_ENABLED: bool = True

    # Worker health check — see app/workers/health.py. A tiny HTTP server
    # the worker process runs alongside its main loop, so Docker (or any
    # external monitor) can tell "still processing events" apart from
    # "hung/crashed but the process technically hasn't exited yet".
    WORKER_HEALTH_PORT: int = 8001
    WORKER_HEARTBEAT_TTL_SECONDS: int = 60

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
