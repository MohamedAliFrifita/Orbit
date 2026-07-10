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


async def test_full_run_reaches_done_with_mocked_stages(monkeypatch):
    """
    Utilise un Analyst mocke ici : depuis la semaine 2, analyst.run() appelle
    le vrai site SEPEM Douai, et un test automatise ne doit jamais dependre
    du reseau (lent, instable, cassant si le site change). Le vrai scraping
    est teste separement dans test_fetch_exhibitor_list.py, contre une fixture
    locale.
    """
    from orbit.agents import analyst
    from orbit.schemas.exhibitor import ExhibitorInput

    async def _mocked_analyst_run(event):
        return [
            ExhibitorInput(id="ex_001", name="Example Corp", booth="A1", raw_description="test"),
            ExhibitorInput(id="ex_002", name="Concurrent SA", booth="A2", raw_description="editeur logiciel"),
        ]

    monkeypatch.setattr(analyst, "run", _mocked_analyst_run)

    state = RunState(client_id="test-client", input=make_input())
    event = SelectedEvent(name="Global Industrie 2026", dates="2026-09-15/18", location="Lyon, FR", exhibitor_count=850)

    state = await run_to_completion(state, event=event)

    assert state.stage == RunStage.DONE
    assert state.selected_event is not None
    assert len(state.exhibitors) > 0
    assert len(state.itinerary) > 0
    scores = [e.potential_score for e in state.exhibitors if e.category != "irrelevant"]
    assert scores == sorted(scores, reverse=True) or len(state.itinerary) <= 1


async def test_select_event_requires_awaiting_selection_stage():
    state = RunState(client_id="test-client", input=make_input())
    event = SelectedEvent(name="X", dates="2026-01-01", location="Paris", exhibitor_count=10)

    with pytest.raises(InvalidTransition):
        select_event(state, event)  # stage encore = SCOUT, pas AWAITING_SELECTION


async def test_analyst_failure_returns_to_awaiting_selection(monkeypatch):
    """Verifie la decision Option A : un echec de l'Analyst ne fait pas planter
    le run et ne bascule pas silencieusement vers un autre evenement - il
    redonne la main a l'utilisateur avec un message d'erreur clair."""
    from orbit.agents import analyst
    from orbit.orchestrator.run import advance
    from orbit.tools.fetch_exhibitor_list import ExhibitorFetchError

    async def _failing_run(event):
        raise ExhibitorFetchError("Site injoignable (simulation de test)")

    monkeypatch.setattr(analyst, "run", _failing_run)

    state = RunState(client_id="test-client", input=make_input())
    event = SelectedEvent(name="Salon Test", dates="2026-01-01", location="Paris", exhibitor_count=10)

    state = await advance(state)  # scout -> awaiting_selection
    state = select_event(state, event)  # awaiting_selection -> analyst
    state = await advance(state)  # analyst (echoue) -> awaiting_selection

    assert state.stage == RunStage.AWAITING_SELECTION
    assert state.error is not None
    assert "injoignable" in state.error
    assert state.selected_event is None
