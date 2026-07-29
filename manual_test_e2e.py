import asyncio
from orbit.schemas.run import RunInput, ICPContext, Objective, RunState, SelectedEvent
from orbit.orchestrator.run import advance, select_event,advance

run_input = RunInput(
    sector="industrial automation",
    region="Europe",
    icp=ICPContext(
        target_client_profile="manufacturers >50 employees, EU",
        objectives=[Objective.FIND_CLIENTS],
    ),
)

state = RunState(client_id="test-manuel-e2e", input=run_input)

async def main():
    global state
    state = await advance(state)
    return state

state = asyncio.run(main())

print(f"Nombre de candidats : {len(state.candidate_events)}")
for i, event in enumerate(state.candidate_events):
    print(f"\n--- Candidat {i} ---")
    print(f"Nom       : {event.name}")
    print(f"Dates     : {event.dates}")
    print(f"Lieu      : {event.location}")
    print(f"Exposants : {event.exhibitor_count}")
    print(f"URL       : {event.source_url}")
    print(f"Note      : {event.relevance_note}")



# Choisir l'index du candidat retenu (ex: 0 pour le premier)
chosen = state.candidate_events[2]
print(f"\n\nCandidat choisi : {chosen.name}")

event = SelectedEvent(
    name=chosen.name,
    dates=chosen.dates,
    location=chosen.location,
    # exhibitor_count et source_url volontairement omis
)

state = select_event(state, event)
print(f"Stage : {state.stage}")
print(f"source_url propage : {state.selected_event.source_url}")





async def run_analyst():
    global state
    state = await advance(state)
    return state

state = asyncio.run(run_analyst())

print(f"\n\nStage : {state.stage}")
print(f"Erreur : {state.error}")
print(f"Nombre d'exposants bruts : {state.raw_exhibitor_count}")

print(f"URL scrapee : {state.selected_event.source_url if state.selected_event else '(reinitialisee)'}")
for ex in state.raw_exhibitors[:5]:
    print(f"- {ex.name} | stand: {ex.booth} | source: {ex.raw_description[:60]}")