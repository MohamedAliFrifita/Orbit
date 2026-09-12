"""Client Groq — Llama 3.3 70B pour Classifier et Planner workers."""


from __future__ import annotations
from groq import AsyncGroq
from orbit.config import settings
GROQ_MODEL = "llama-3.3-70b-versatile"
_client: AsyncGroq | None = None
def get_groq_client() -> AsyncGroq:
    global _client
    if _client is None:
        _client = AsyncGroq(api_key=settings.groq_api_key)
    return _client