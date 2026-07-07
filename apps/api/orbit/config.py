from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://orbit:orbit@localhost:5432/orbit"
    redis_url: str = "redis://localhost:6379/0"
    anthropic_api_key: str = ""
    enrichment_api_key: str = ""
    email_provider_api_key: str = ""
    env: str = "development"


settings = Settings()
