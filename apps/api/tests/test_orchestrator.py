import pytest

from orbit.orchestrator.run import InvalidTransition, advance, run_to_completion, select_event
from orbit.schemas.run import ICPContext, Objective, RunInput, RunStage, RunState, SelectedEvent


def make_input() -> RunInput:
    return RunInput(
        sector="industrial automation",
        icp=ICPContext(
            target_client_profile="manufacturers >50 employees, EU",
            objectives=[Objective.FIND_CLIENTS],
        ),
        region="France",
    )


async def test_scout_stage_produces_candidates():
    state = RunState(client_id="test-client", input=make_input())
    state = await advance(state)

    assert state.stage == RunStage.AWAITING_SELECTION
    assert len(state.candidate_events) > 0


async def test_cannot_advance_while_awaiting_selection():
    state = RunState(client_id="test-client", input=make_input())
    state = await advance(state)

    with pytest.raises(InvalidTransition):
        await advance(state)


async def test_full_run_reaches_done_with_mocked_stages():
    state = RunState(client_id="test-client", input=make_input())
    event = SelectedEvent(name="Global Industrie 2026", dates="2026-09-15/18", location="Lyon, FR", exhibitor_count=850)

    state = await run_to_completion(state, event=event)

    assert state.stage == RunStage.DONE
    assert state.selected_event is not None
    assert len(state.exhibitors) > 0
    assert len(state.itinerary) > 0
    # l'itineraire doit etre trie par potential_score decroissant
    score_map = {e.exhibitor_id: e.potential_score for e in state.exhibitors}
    itinerary_scores = [score_map[stop.exhibitor_id] for stop in state.itinerary]
    assert itinerary_scores == sorted(itinerary_scores, reverse=True) or len(state.itinerary) <= 1


async def test_select_event_requires_awaiting_selection_stage():
    state = RunState(client_id="test-client", input=make_input())
    event = SelectedEvent(name="X", dates="2026-01-01", location="Paris", exhibitor_count=10)

    with pytest.raises(InvalidTransition):
        select_event(state, event)  # stage encore = SCOUT, pas AWAITING_SELECTION
