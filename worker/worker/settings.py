import os

from arq.connections import RedisSettings

DEFAULT_REDIS_URL = "redis://redis:6379/0"


def redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(os.getenv("REDIS_URL", DEFAULT_REDIS_URL))


def plantuml_server_url() -> str:
    return os.getenv("PLANTUML_SERVER_URL", "http://plantuml:8080")
