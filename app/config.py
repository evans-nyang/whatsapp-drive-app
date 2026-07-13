from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # WhatsApp
    whatsapp_app_secret: str
    whatsapp_verify_token: str
    whatsapp_access_token: str
    whatsapp_phone_number_id: str
    whatsapp_api_version: str = "v20.0"

    # Google Drive
    google_service_account_json: str
    google_drive_root_folder_id: str

    # Postgres
    database_url: str

    # Redis
    redis_url: str

    # RabbitMQ
    rabbitmq_url: str
    media_events_exchange: str = "media.events"

    # App
    log_level: str = "INFO"
    environment: str = "development"

    @property
    def whatsapp_graph_base_url(self) -> str:
        return f"https://graph.facebook.com/{self.whatsapp_api_version}"


@lru_cache
def get_settings() -> Settings:
    """Settings are cached per-process — safe because env vars don't change at runtime."""
    return Settings()
