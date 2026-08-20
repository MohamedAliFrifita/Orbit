"""
debug_link_extraction.py — outil de diagnostic manuel (pas un test pytest).

Utilite : inspecter precisement ce que Playwright + _extract_links() recuperent
vraiment pour une homepage donnee, et si _find_exhibitor_link_heuristic()
trouve ou non un candidat parmi ces liens - sans avoir a relancer tout le
pipeline Analyst via l'API pour deboguer un cas d'echec de localisation
de lien (voir cas reel VivaTech, ou l'heuristique + le LLM ont echoue
malgre un lien "Exhibitors" visible dans le menu du site).

Usage :
    python eval/debug_link_extraction.py https://vivatechnology.com
"""

from __future__ import annotations

import asyncio
import sys

from orbit.tools.fetch_exhibitor_list import (
    _EXHIBITOR_KEYWORDS,
    _extract_links,
    _find_exhibitor_link_heuristic,
    _render_page,
)

# Seuil arbitraire de diagnostic : en dessous, la page est probablement
# un mur de cookies / coquille JS vide plutot qu'une vraie homepage rendue
_SUSPICIOUSLY_SMALL_HTML = 8000


async def main(url: str) -> None:
    print(f"--- Rendu de {url} avec Playwright ---")
    html = await _render_page(url)
    print(f"Taille du HTML rendu : {len(html)} caracteres\n")

    if len(html) < _SUSPICIOUSLY_SMALL_HTML:
        print(
            f"ATTENTION: HTML anormalement court (< {_SUSPICIOUSLY_SMALL_HTML} caracteres) — "
            "probablement un mur de consentement cookies ou une coquille JS "
            "non totalement rendue. Contenu brut ci-dessous :\n"
        )
        print("=" * 70)
        print(html)
        print("=" * 70)
        print()

    links = _extract_links(html, url)
    print(f"--- {len(links)} liens extraits (texte visible non vide) ---\n")

    if not links:
        print("AUCUN LIEN TROUVE. Causes possibles :")
        print("  - Mur de consentement cookies affiche par-dessus la vraie page")
        print("  - Le menu de navigation est injecte seulement au clic (pas dans le DOM initial)")
        print("  - domcontentloaded a capture la page avant que le contenu ne soit monte par le JS")
        return

    for i, link in enumerate(links):
        print(f"{i:3d}. [{link['text'][:60]!r}] -> {link['href']}")

    print("\n--- Verification manuelle des mots-cles ---")
    matched = [
        link for link in links
        if any(kw in link["text"].lower() or kw in link["href"].lower() for kw in _EXHIBITOR_KEYWORDS)
    ]
    print(f"{len(matched)} lien(s) matchant _EXHIBITOR_KEYWORDS :")
    for link in matched:
        print(f"  - [{link['text']!r}] -> {link['href']}")

    print("\n--- Resultat de _find_exhibitor_link_heuristic() ---")
    result = _find_exhibitor_link_heuristic(links)
    if result is None:
        print("None (0 ou plusieurs matches - ambigu ou aucun candidat)")
    else:
        print(f"Retenu : {result}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python eval/debug_link_extraction.py <url>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))