"""Client Groq pour l'Orchestrateur (GPT-OSS-120B)."""

from __future__ import annotations

from groq import AsyncGroq
from orbit.config import settings

# Modèle Groq utilisé pour le Planning et l'Orchestration
GROK_MODEL = "openai/gpt-oss-120b"
_client: AsyncGroq | None = None


def get_grok_client() -> AsyncGroq:
    global _client
    if _client is None:
        _client = AsyncGroq(api_key=settings.groq_api_key)
    return _client