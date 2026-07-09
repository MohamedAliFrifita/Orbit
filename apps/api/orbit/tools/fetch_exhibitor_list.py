"""
fetch_exhibitor_list — Analyst tool reel (semaine 2).

Cas de test choisi (Objectif 1) : SEPEM Douai 2026
https://douai.sepem-industries.com/content/liste-des-exposants

Pourquoi ce site : page HTML statique (verifie via "Afficher le code source"),
les noms d'exposants sont directement presents dans le HTML brut, pas de
rendu JavaScript necessaire (contrairement a Global Industrie, ecarte pour
cette raison - voir la discussion Objectif 1).

Pourquoi une extraction par TEXTE plutot que par selecteur CSS precis :
sans avoir inspecte le DOM reel dans un navigateur (balises/classes exactes),
on parse le texte visible de la page avec une expression reguliere qui
capture le pattern observe : "NOM" + "Grand palais"/"Novaxia bas" (optionnel)
+ " - Stand " + code de stand (optionnel, parfois vide ou multiple).
Cette approche est plus robuste a de petites variations de markup qu'un
selecteur CSS devine sans avoir vu le vrai DOM. A affiner si le parsing
rate des exposants une fois teste contre la vraie page.
"""

from __future__ import annotations

import re

import httpx
from bs4 import BeautifulSoup

from orbit.schemas.exhibitor import ExhibitorInput
from orbit.schemas.run import SelectedEvent

SEPEM_DOUAI_URL = "https://douai.sepem-industries.com/content/liste-des-exposants"

# Pattern observe sur la vraie page : nom colle directement au lieu + " - Stand " + code
# Exemples reels :
#   "2ADIS Grand palais - Stand B26"
#   "3 AXES SASGrand palais - Stand G32"
#   "AMITECGrand palais - Stand"                (pas de numero de stand)
#   "ATIPIK 3D PRINT - Stand"                    (pas de nom de hall)
#   "KIO SOFTWAREGrand palais - Stand C104,B55"  (deux stands)
_ENTRY_PATTERN = re.compile(
    r"^(?P<name>.+?)"
    r"(?:(?P<hall>Grand palais|Novaxia bas))?"
    r"\s*-\s*Stand\s*(?P<stand>[A-Za-z0-9,]*)$"
)


class ExhibitorFetchError(Exception):
    """
    Levee quand la liste d'exposants ne peut pas etre recuperee ou parsee.

    Utilite (voir Objectif 4 - Option A) : cette exception permet a
    l'orchestrateur de distinguer un vrai probleme (site injoignable,
    structure de page cassee) d'une liste simplement vide, et de renvoyer
    le run au stage AWAITING_SELECTION avec un message clair plutot que
    de planter ou de continuer silencieusement avec des donnees fausses.
    """

    pass


async def fetch_exhibitor_list(event: SelectedEvent, url: str = SEPEM_DOUAI_URL) -> list[ExhibitorInput]:
    """
    Recupere et parse la liste d'exposants pour l'evenement SEPEM Douai.

    Leve ExhibitorFetchError si :
    - le site ne repond pas (timeout, erreur reseau, code HTTP d'erreur)
    - aucun exposant n'a pu etre extrait (structure de page probablement changee)
    """
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ExhibitorFetchError(
            f"Impossible d'acceder a la page exposants ({url}): {exc}"
        ) from exc

    exhibitors = _parse_exhibitors(response.text)

    if not exhibitors:
        raise ExhibitorFetchError(
            f"Aucun exposant trouve sur {url} - la structure de la page a probablement change, "
            "verifier le parsing (fetch_exhibitor_list.py)."
        )

    return exhibitors


def _parse_exhibitors(html: str) -> list[ExhibitorInput]:
    soup = BeautifulSoup(html, "html.parser")

    # On tente d'abord les elements de liste (structure la plus probable),
    # et on retombe sur toutes les lignes de texte si rien n'est trouve.
    candidates = soup.select("li") or soup.select("p")

    exhibitors: list[ExhibitorInput] = []
    seen_ids: set[str] = set()

    for i, el in enumerate(candidates):
        text = el.get_text(strip=True)
        match = _ENTRY_PATTERN.match(text)
        if not match:
            continue

        name = match.group("name").strip()
        hall = match.group("hall") or ""
        stand = match.group("stand") or ""

        if not name:
            continue

        exhibitor_id = f"sepem_{i:04d}"
        if exhibitor_id in seen_ids:
            continue
        seen_ids.add(exhibitor_id)

        booth = f"{hall} - Stand {stand}".strip(" -") if (hall or stand) else None

        exhibitors.append(
            ExhibitorInput(
                id=exhibitor_id,
                name=name,
                booth=booth,
                raw_description=text,
            )
        )

    return exhibitors