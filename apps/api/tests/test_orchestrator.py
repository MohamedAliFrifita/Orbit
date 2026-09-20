"""
Tests de l'orchestrateur (Architecture 3 sous-phases : Planning, Working, Judging).

Tous les appels LLM (Groq pour Planning, Gemini pour Scout/Analyst, Mistral pour Judge)
sont mockés pour garantir des tests unitaires déterministes, rapides et hors réseau.
"""

from unittest.mock import AsyncMock
import pytest

from orbit.orchestrator.run import InvalidTransition, advance, select_event
from orbit.schemas.judge import JudgeVerdict
from orbit.schemas.run import (
    EventCandidate,
    ICPContext,
    Objective,
    RunInput,
    RunStage,
    RunState,
    SelectedEvent,
    StagePlan,
)


def make_input() -> RunInput:
    return RunInput(
        sector="industrial automation",
        icp=ICPContext(
            target_client_profile="manufacturers >50 employees, EU",
            objectives=[Objective.FIND_CLIENTS],
        ),
        region="France",
    )


def _mock_plan(prompt="mock prompt", criteria=None):
    return StagePlan(
        prompt_worker=prompt,
        success_criteria=criteria or {"min_candidates": 1},
    )



def _mock_verdict(verdict="PASS", score=9.0, reasoning="OK", suggestions=None):
    return JudgeVerdict(
        verdict=verdict,
        score=score,
        reasoning=reasoning,
        suggestions=suggestions,
    )



@pytest.fixture(autouse=True)
def mock_planning_and_judge(monkeypatch):
    """Par défaut, le planning génère un plan valide et le Judge renvoie PASS."""
    from orbit.orchestrator import planning
    from orbit.judge import run as judge_mod

    async def _fake_plan(state, stage):
        return _mock_plan()

    async def _fake_judge(judge_input, attempt_number=1):
        return _mock_verdict("PASS")

    monkeypatch.setattr(planning, "plan_stage", _fake_plan)
    monkeypatch.setattr(judge_mod, "judge", _fake_judge)


def _mock_scout(monkeypatch, events=None):
    from orbit.agents import scout

    default_events = events or [
        EventCandidate(
            name="Salon Mocke 2026",
            dates="2026-09-15/18",
            location="Lyon, FR",
            exhibitor_count=100,
            source_url="https://exemple-mocke.fr/exposants",
        )
    ]

    async def _mocked_scout_run(run_input, prompt_override=None):
        return default_events

    monkeypatch.setattr(scout, "run", _mocked_scout_run)
    return default_events


async def test_scout_stage_produces_candidates_and_saves_plan(monkeypatch):
    _mock_scout(monkeypatch)

    events_published = []
    async def publish(event):
        events_published.append(event)

    state = RunState(client_id="test-client", input=make_input())
    state = await advance(state, publish=publish)

    assert state.stage == RunStage.AWAITING_SELECTION
    assert len(state.candidate_events) == 1
    assert "scout" in state.stage_plans
    # Vérifie que les sous-phases ont été publiées via SSE
    subphases = [e.get("subphase") for e in events_published if "subphase" in e]
    assert "planning" in subphases
    assert "working" in subphases
    assert "judging" in subphases


async def test_cannot_advance_while_awaiting_selection(monkeypatch):
    _mock_scout(monkeypatch)

    state = RunState(client_id="test-client", input=make_input())
    state = await advance(state)

    assert state.stage == RunStage.AWAITING_SELECTION
    with pytest.raises(InvalidTransition):
        await advance(state)


async def test_select_event_transitions_to_analyst():
    state = RunState(client_id="test-client", input=make_input())
    state.stage = RunStage.AWAITING_SELECTION
    event = SelectedEvent(
        name="Global Industrie", dates="2026-09-15", location="Lyon", exhibitor_count=500
    )

    state = select_event(state, event)
    assert state.stage == RunStage.ANALYST
    assert state.selected_event.name == "Global Industrie"


async def test_select_event_requires_awaiting_selection_stage():
    state = RunState(client_id="test-client", input=make_input())
    event = SelectedEvent(name="X", dates="2026-01-01", location="Paris", exhibitor_count=10)

    with pytest.raises(InvalidTransition):
        select_event(state, event)


async def test_source_url_propagates_from_candidate_to_selected_event(monkeypatch):
    _mock_scout(monkeypatch)

    state = RunState(client_id="test-client", input=make_input())
    state = await advance(state)

    state.candidate_events = [
        EventCandidate(
            name="Salon Reel",
            dates="2026-05-01",
            location="Paris, FR",
            source_url="https://exemple-salon.fr/exposants",
        )
    ]

    event = SelectedEvent(name="Salon Reel", dates="2026-05-01", location="Paris, FR", exhibitor_count=100)
    state = select_event(state, event)

    assert state.selected_event.source_url == "https://exemple-salon.fr/exposants"


async def test_analyst_failure_returns_to_awaiting_selection(monkeypatch):
    from orbit.agents import analyst
    from orbit.tools.fetch_exhibitor_list import ExhibitorFetchError

    _mock_scout(monkeypatch)

    async def _failing_run(event, prompt_override=None):
        raise ExhibitorFetchError("Site injoignable (simulation de test)")

    monkeypatch.setattr(analyst, "run", _failing_run)

    state = RunState(client_id="test-client", input=make_input())
    event = SelectedEvent(name="Salon Test", dates="2026-01-01", location="Paris", exhibitor_count=10)

    state = await advance(state)
    state = select_event(state, event)
    state = await advance(state)

    assert state.stage == RunStage.AWAITING_SELECTION
    assert state.error is not None
    assert "injoignable" in state.error
    assert state.selected_event is None


async def test_judge_refine_loop_triggers_forced_pass(monkeypatch):
    """Vérifie que des verdicts REFINE successifs déclenchent un force-PASS avec low_confidence."""
    from orbit.judge import run as judge_mod
    from orbit.orchestrator import planning

    _mock_scout(monkeypatch)

    # Le Judge demande toujours REFINE
    async def _refine_judge(judge_input, attempt_number=1):
        return _mock_verdict("REFINE", score=4.0, reasoning="Insuffisant")

    async def _fake_refine_plan(state, plan, verdict):
        return plan

    monkeypatch.setattr(judge_mod, "judge", _refine_judge)
    monkeypatch.setattr(planning, "refine_plan", _fake_refine_plan)

    state = RunState(client_id="test-client", input=make_input())
    state = await advance(state)

    assert state.stage == RunStage.AWAITING_SELECTION
    assert state.low_confidence is True
    assert "scout" in state.low_confidence_stages


async def test_judge_rework_returns_to_previous_stage(monkeypatch):
    """Vérifie qu'un verdict REWORK au stage ANALYST renvoie au SCOUT."""
    from orbit.agents import analyst
    from orbit.judge import run as judge_mod
    from orbit.schemas.exhibitor import ExhibitorInput

    _mock_scout(monkeypatch)

    async def _mock_analyst(event, prompt_override=None):
        return [ExhibitorInput(id="1", name="Ex1", booth="A", raw_description="desc")]

    async def _rework_judge(judge_input, attempt_number=1):
        return _mock_verdict("REWORK", score=2.0, reasoning="Mauvais salon")

    monkeypatch.setattr(analyst, "run", _mock_analyst)
    monkeypatch.setattr(judge_mod, "judge", _rework_judge)

    state = RunState(client_id="test-client", input=make_input())
    state = await advance(state)  # SCOUT -> AWAITING_SELECTION

    event = SelectedEvent(name="Salon Test", dates="2026-01-01", location="Paris", exhibitor_count=10)
    state = select_event(state, event)  # -> ANALYST
    state = await advance(state)  # REWORK au stage ANALYST -> retour au SCOUT

    assert state.stage == RunStage.SCOUT
    assert state.retry_counts.get("rework_analyst") == 1