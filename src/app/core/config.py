from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application configuration, sourced from environment variables / .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    app_name: str = "AsyncPaymentProcessor"
    environment: str = "local"
    log_level: str = "INFO"
    log_json: bool = False

    # --- Security ---
    api_key: str = Field(default="dev-api-key", description="Static key required in X-API-Key header")

    # --- Database ---
    database_url: str = Field(
        default="postgresql+asyncpg://payments:payments@localhost:5432/payments",
        description="Async SQLAlchemy connection string",
    )
    db_pool_size: int = 10
    db_max_overflow: int = 10
    db_echo: bool = False

    # --- RabbitMQ ---
    rabbitmq_url: str = Field(default="amqp://guest:guest@localhost:5672/")
    rabbitmq_prefetch_count: int = 10

    # --- Outbox relay ---
    outbox_poll_interval_seconds: float = 1.0
    outbox_batch_size: int = 20

    # --- Payment processing emulation ---
    gateway_min_delay_seconds: float = 2.0
    gateway_max_delay_seconds: float = 5.0
    gateway_success_rate: float = 0.9

    # --- Message-level retry / DLQ ---
    message_max_attempts: int = 3
    message_retry_base_delay_ms: int = 2000

    # --- Webhook delivery ---
    webhook_max_attempts: int = 3
    webhook_timeout_seconds: float = 5.0
    webhook_circuit_breaker_failure_threshold: int = 5
    webhook_circuit_breaker_reset_seconds: float = 30.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
