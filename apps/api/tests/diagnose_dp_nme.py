import asyncio
from orbit.tools.fetch_exhibitor_list import _render_page, _clean_html_to_text

async def main():
    html = await _render_page("https://dp-nme.fieramilano.it/en/page/espositori")
    print(f"Taille HTML brut : {len(html)} caracteres")

    text = _clean_html_to_text(html)
    print(f"Taille texte nettoye : {len(text)} caracteres")
    print("--- 1000 premiers caracteres du texte nettoye ---")
    print(text[:1000])
    print("--- 'A-TONO' present dans le texte ? ---")
    print("A-TONO" in text)

asyncio.run(main())