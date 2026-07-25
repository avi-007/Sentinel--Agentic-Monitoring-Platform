"""Typed env-var settings shared across services, built on pydantic-settings.

Each service defines its own `*Settings` subclass (see services/*/app/config.py)
that adds service-specific fields on top of these shared blocks. Every field has
a hardcoded default matching .env.example, so any service also runs standalone
(e.g. under pytest) without a .env file present.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class KafkaSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    kafka_bootstrap_servers: str = "kafka:9092"
    topic_telemetry_raw: str = "telemetry.raw"
    topic_alerts_triggered: str = "alerts.triggered"


class PostgresSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "sentinel"
    postgres_user: str = "sentinel"
    postgres_password: str = "sentinel_dev_password"

    @property
    def dsn(self) -> str:
        return (
            f"host={self.postgres_host} port={self.postgres_port} "
            f"dbname={self.postgres_db} user={self.postgres_user} "
            f"password={self.postgres_password}"
        )


class BaseServiceSettings(KafkaSettings, PostgresSettings):
    model_config = SettingsConfigDict(extra="ignore")

    log_level: str = "INFO"
