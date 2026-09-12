"""
Pipeline autonome + SSE streaming.

Après select_event(), le pipeline tourne en tâche de fond (asyncio.create_task).
Les events sont publiés dans Redis (channel run:{run_id}:events).
Le client SSE consomme ce channel en temps réel.

Pause : l'API écrit run:{run_id}:pause_requested dans Redis.
         Le pipeline vérifie ce flag à chaque sous-phase et s'arrête proprement.
"""

from __future__ import annotations

import asyncio
import json
import time

import redis.asyncio as aioredis
from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from orbit.config import settings
from orbit.orchestrator.run import advance, select_event
from orbit.schemas.run import RunState

router = APIRouter(tags=["stream"])

# Store en mémoire (à remplacer par Postgres en production)
_RUNS: dict[str, RunState] = {}

# Pool Redis partagé
_redis_pool: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis_pool


async def _publish(run_id: str, event: dict) -> None:
    """Publie un événement SSE dans le canal Redis du run."""
    redis = get_redis()
    await redis.publish(f"run:{run_id}:events", json.dumps(event))


async def _run_pipeline_background(run_id: str) -> None:
    """
    Tâche de fond : fait avancer le run jusqu'à DONE, FAILED ou PAUSED.
    Vérifie le flag de pause Redis à chaque étape.
    """
    from orbit.schemas.run import RunStage

    redis = get_redis()

    async def publish(event: dict) -> None:
        await _publish(run_id, event)

    state = _RUNS.get(run_id)
    if state is None:
        return

    while state.stage not in (
        RunStage.DONE, RunStage.FAILED, RunStage.AWAITING_SELECTION
    ):
        # Vérifier pause avant chaque stage
        pause_requested = await redis.exists(f"run:{run_id}:pause_requested")
        if pause_requested:
            state.paused = True
            _RUNS[run_id] = state
            await publish({"event": "run_paused", "stage": state.stage.value})
            await redis.delete(f"run:{run_id}:pause_requested")
            return

        state = await advance(state, publish=publish)
        _RUNS[run_id] = state

        # Si le stage a causé une pause interne (sous-phase)
        if state.paused:
            await publish({"event": "run_paused", "stage": state.stage.value,
                           "subphase": state.paused_at_subphase.value if state.paused_at_subphase else None})
            return

    _RUNS[run_id] = state
    if state.stage == RunStage.DONE:
        await publish({"event": "run_done", "low_confidence": state.low_confidence})


def start_pipeline(run_id: str) -> None:
    """Lance le pipeline en tâche de fond asyncio."""
    asyncio.create_task(_run_pipeline_background(run_id))


@router.get("/runs/{run_id}/stream")
async def stream_run(run_id: str) -> EventSourceResponse:
    """SSE endpoint — envoie les événements du pipeline en temps réel."""

    async def event_generator():
        redis = get_redis()
        pubsub = redis.pubsub()
        await pubsub.subscribe(f"run:{run_id}:events")

        timeout_s = 600   # 10 minutes max par connexion SSE
        deadline = time.monotonic() + timeout_s

        try:
            while time.monotonic() < deadline:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg and msg["type"] == "message":
                    data = json.loads(msg["data"])
                    yield {"data": json.dumps(data)}
                    if data.get("event") in ("run_done", "run_paused", "stage_error"):
                        break
                await asyncio.sleep(0.05)
        finally:
            await pubsub.unsubscribe(f"run:{run_id}:events")

    return EventSourceResponse(event_generator())