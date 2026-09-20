"""
Tests unitaires de l'exportation PDF de l'itinéraire.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from orbit.api.main import app
from orbit.api.stream import _RUNS
from orbit.db.models import User
from orbit.schemas.run import (
    ICPContext,
    Objective,
    RunInput,
    RunStage,
    RunState,
    SelectedEvent,
)


@pytest.fixture
def fake_user():
    return User(id="user-123", email="agent@orbit.ai", hashed_password="pw")


@pytest.fixture(autouse=True)
def override_user(fake_user):
    from orbit.api.deps import get_current_user
    app.dependency_overrides[get_current_user] = lambda: fake_user
    yield
    app.dependency_overrides.clear()


def make_run(stage=RunStage.DONE, client_id="user-123"):
    return RunState(
        run_id="run-pdf-test",
        client_id=client_id,
        stage=stage,
        input=RunInput(
            sector="AI",
            region="Europe",
            icp=ICPContext(
                target_client_profile="CTO B2B",
                objectives=[Objective.FIND_CLIENTS],
            ),
        ),
        selected_event=SelectedEvent(
            name="Salon IA 2026",
            dates="2026-05-10/12",
            location="Paris",
            exhibitor_count=100,
        ),
        itinerary=[
            {
                "order": 1,
                "time_slot": "09:30 - 10:15",
                "exhibitor_name": "DeepTech AI",
                "booth": "Hall 1, Stand A12",
                "category": "client",
                "potential_score": 0.95,
                "visit_objective": "Présenter solution B2B",
                "talking_points": ["Point 1", "Point 2"],
            }
        ],
    )


async def test_export_pdf_not_found():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/runs/unknown-id/export/pdf")
        assert res.status_code == 404


async def test_export_pdf_not_done_returns_409():
    _RUNS["run-scout"] = make_run(stage=RunStage.SCOUT)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/runs/run-scout/export/pdf")
        assert res.status_code == 409
        assert "pas encore terminé" in res.json()["detail"]


async def test_export_pdf_done_returns_valid_pdf():
    run = make_run(stage=RunStage.DONE)
    _RUNS[run.run_id] = run

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get(f"/runs/{run.run_id}/export/pdf")
        assert res.status_code == 200
        assert res.headers["content-type"] == "application/pdf"
        assert res.content.startswith(b"%PDF")
