"""FastAPI app — architecture nouvelle avec auth JWT, SSE, pipeline autonome."""

from __future__ import annotations

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())  # type: ignore

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from orbit.api import auth as auth_router
from orbit.api import export as export_router
from orbit.api import stream as stream_module
from orbit.api.deps import get_current_user
from orbit.db.models import User
from orbit.orchestrator.run import InvalidTransition, advance, select_event
from orbit.schemas.run import RunInput, RunState, SelectedEvent, RunStage

app = FastAPI(title="ORBIT API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_origin_regex=r"https://.*\.app\.github\.dev",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth_router.router)
app.include_router(stream_module.router)
app.include_router(export_router.router)

# Store en mémoire — à remplacer par Postgres (Phase A3)
RUNS = stream_module._RUNS


# ── Endpoints publics ─────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": "0.2.0"}


# ── Endpoints protégés ────────────────────────────────────────────────────────

@app.post("/runs", response_model=RunState)
async def create_run(
    run_input: RunInput,
    current_user: User = Depends(get_current_user),
) -> RunState:
    """Crée un run et lance le Scout (sous-phases Planning→Working→Judging)."""
    state = RunState(client_id=current_user.id, input=run_input)

    async def publish(event: dict) -> None:
        await stream_module._publish(state.run_id, event)

    state = await advance(state, publish=publish)
    RUNS[state.run_id] = state
    return state


@app.get("/runs", response_model=list[RunState])
async def list_runs(
    current_user: User = Depends(get_current_user),
) -> list[RunState]:
    """Retourne tous les runs de l'utilisateur courant."""
    return [r for r in RUNS.values() if r.client_id == current_user.id]


@app.get("/runs/{run_id}", response_model=RunState)
async def get_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
) -> RunState:
    state = RUNS.get(run_id)
    if state is None or state.client_id != current_user.id:
        raise HTTPException(status_code=404, detail="Run introuvable")
    return state


@app.post("/runs/{run_id}/select-event", response_model=RunState)
async def choose_event(
    run_id: str,
    event: SelectedEvent,
    current_user: User = Depends(get_current_user),
) -> RunState:
    """
    Sélection de l'événement par l'utilisateur.
    Déclenche immédiatement le pipeline autonome (ANALYST → CLASSIFIER → PLANNER).
    """
    state = RUNS.get(run_id)
    if state is None or state.client_id != current_user.id:
        raise HTTPException(status_code=404, detail="Run introuvable")
    try:
        state = select_event(state, event)
    except InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    RUNS[run_id] = state

    # Lance le pipeline autonome en tâche de fond
    stream_module.start_pipeline(run_id)
    return state


@app.post("/runs/{run_id}/pause", response_model=RunState)
async def pause_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
) -> RunState:
    """Demande une pause du pipeline après la sous-phase en cours."""
    state = RUNS.get(run_id)
    if state is None or state.client_id != current_user.id:
        raise HTTPException(status_code=404, detail="Run introuvable")
    redis = stream_module.get_redis()
    await redis.set(f"run:{run_id}:pause_requested", "1", ex=3600)
    return state


@app.post("/runs/{run_id}/resume", response_model=RunState)
async def resume_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
) -> RunState:
    """Reprend le pipeline depuis l'état de pause."""
    state = RUNS.get(run_id)
    if state is None or state.client_id != current_user.id:
        raise HTTPException(status_code=404, detail="Run introuvable")
    if not state.paused:
        raise HTTPException(status_code=409, detail="Le run n'est pas en pause")

    redis = stream_module.get_redis()
    await redis.delete(f"run:{run_id}:pause_requested")
    state.paused = False
    state.paused_at_stage = None
    state.paused_at_subphase = None
    RUNS[run_id] = state

    stream_module.start_pipeline(run_id)
    return state


@app.post("/runs/{run_id}/retry-stage", response_model=RunState)
async def retry_stage(
    run_id: str,
    current_user: User = Depends(get_current_user),
) -> RunState:
    """Relance le stage actuel depuis sa sous-phase Planning (disponible en pause)."""
    state = RUNS.get(run_id)
    if state is None or state.client_id != current_user.id:
        raise HTTPException(status_code=404, detail="Run introuvable")
    if not state.paused:
        raise HTTPException(status_code=409, detail="Disponible uniquement en pause")

    # Réinitialise les compteurs du stage courant
    if state.paused_at_stage:
        stage_key = state.paused_at_stage.value
        state.retry_counts.pop(stage_key, None)
        state.stage_plans.pop(stage_key, None)

    state.paused = False
    state.paused_at_stage = None
    state.paused_at_subphase = None
    RUNS[run_id] = state

    stream_module.start_pipeline(run_id)
    return state