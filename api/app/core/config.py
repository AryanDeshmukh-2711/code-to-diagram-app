from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, populated from the environment.

    Defaults here match the service names in docker-compose so the stack boots
    with an empty .env. Anything genuinely secret has no default.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_env: str = "local"
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://asa:asa@postgres:5432/asa"
    redis_url: str = "redis://redis:6379/0"
    plantuml_server_url: str = "http://plantuml:8080"

    # Comma-separated. Defaults to local dev's web origin; a hosted deployment
    # sets this to its real public web domain.
    cors_allowed_origins: str = "http://localhost:3000"

    # Per-dependency ceiling for the /health probes. Kept short so an unhealthy
    # dependency surfaces as a fast 503 rather than a hanging request.
    health_probe_timeout_seconds: float = 3.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
