from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Infrastructure
    database_url: str = "postgresql+asyncpg://orbit:orbit@localhost:5432/orbit"
    redis_url: str = "redis://localhost:6379/0"
    env: str = "development"

    # Providers existants
    gemini_api_key: str = ""
    enrichment_api_key: str = ""
    email_provider_api_key: str = ""

    # Nouveaux providers LLM
    grok_api_key: str = ""          # xAI — Orchestrateur Planning
    groq_api_key: str = ""          # Groq — Classifier + Planner workers
    mistral_api_key: str = ""       # Mistral — Judge

    # Auth JWT
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_expire_minutes: int = 1440   # 24h
    jwt_refresh_expire_days: int = 7


settings = Settings()