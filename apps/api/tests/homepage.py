import asyncio
from orbit.tools.fetch_exhibitor_list import _render_page
html = asyncio.run(_render_page('https://www.nextmobilityexhibition.com/en/'))
print(f'{len(html)} caracteres recuperes')