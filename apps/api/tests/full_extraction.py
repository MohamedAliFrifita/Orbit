import asyncio
from orbit.tools.fetch_exhibitor_list import fetch_exhibitor_list
from orbit.schemas.run import SelectedEvent

event = SelectedEvent(name='Next Mobility Exhibition 2026', dates='2026-05-13/16', location='Milan, Italy', source_url='https://www.nextmobilityexhibition.com/en/')
result = asyncio.run(fetch_exhibitor_list(event))
print(f'{len(result)} exposants recuperes --pipeline complet)')