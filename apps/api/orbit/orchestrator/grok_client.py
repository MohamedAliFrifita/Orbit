"""Client xAI GROK — compatible API OpenAI."""

from __future__ import annotations

from openai import AsyncOpenAI

from orbit.config import settings

GROK_MODEL = "grok-2-latest"
_client: AsyncOpenAI | None = None


def get_grok_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.grok_api_key,
            base_url="https://api.x.ai/v1",
        )
    return _client