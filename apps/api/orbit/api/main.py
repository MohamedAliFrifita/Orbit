"""
FastAPI app - semaine 1.

Le store est en memoire (dict) pour l'instant : suffisant pour tester
la state machine de bout en bout. SEMAINE 2 : remplacer RUNS par de vraies
lectures/ecritures via orbit.db.models (voir persist() dans orchestrator/run.py,
a creer a ce moment-la).
"""

import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())  # type: ignore

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from orbit.orchestrator.run import InvalidTransition, advance, select_event
from orbit.schemas.run import RunInput, RunState, SelectedEvent

app = FastAPI(title="ORBIT API", version="0.1.0")

# CORS : autoriser le frontend Next.js en dev local (semaine 4)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_origin_regex=r"https://.*\.app\.github\.dev",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# TODO(semaine 2): remplacer par la persistance Postgres
RUNS: dict[str, RunState] = {}


@app.post("/runs", response_model=RunState)
async def create_run(run_input: RunInput, client_id: str = "demo-client") -> RunState:
    state = RunState(client_id=client_id, input=run_input)
    state = await advance(state)  # scout -> awaiting_selection
    RUNS[state.run_id] = state
    return state


@app.get("/runs/{run_id}", response_model=RunState)
async def get_run(run_id: str) -> RunState:
    state = RUNS.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Run introuvable")
    return state


@app.post("/runs/{run_id}/select-event", response_model=RunState)
async def choose_event(run_id: str, event: SelectedEvent) -> RunState:
    state = RUNS.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Run introuvable")
    try:
        state = select_event(state, event)
    except InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    RUNS[run_id] = state
    return state


@app.post("/runs/{run_id}/advance", response_model=RunState)
async def advance_run(run_id: str) -> RunState:
    """Fait avancer le run d'un stage. SEMAINE 2+: ceci deviendra un job de queue,
    plus un endpoint synchrone (voir orbit-coding-guide.md §7)."""
    state = RUNS.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Run introuvable")
    try:
        state = await advance(state)
    except InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    RUNS[run_id] = state
    return state


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
