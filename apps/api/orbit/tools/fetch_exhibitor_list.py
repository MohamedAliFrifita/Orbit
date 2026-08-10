"""
fetch_exhibitor_list - Analyst tool reel.

SEMAINE 2, Objectif 5 (v2) : pipeline a 3 niveaux, du moins cher au plus robuste.

Niveau 1 - Parsing statique par regex (rapide, gratuit) : calibre sur le pattern
observe sur SEPEM Douai. Fonctionne uniquement si un pattern texte connu matche.

Niveau 2 - Extraction par LLM (Gemini, response_schema natif) : declenche
uniquement si le Niveau 1 ne trouve aucun exposant. Plus robuste a une structure
de page inconnue, mais coute un appel LLM (quota limite - voir Decision 4 de
l'echange precedent : PAS de re-prompt correctif ici, contrairement au Scout,
car response_schema garantit deja une sortie conforme).

Niveau 3 - ExhibitorFetchError (dernier recours) : si meme le LLM ne trouve
rien dans le texte de la page, c'est probablement un site dont le contenu est
genere par JavaScript (le texte utile n'existe simplement pas dans la reponse
HTTP recue - un LLM ne peut pas extraire une info qui n'est pas dans le texte
fourni). Ce cas precis appellera Playwright dans une iteration future, si on
l'observe reellement (voir orbit-contexte-semaine2.md).
"""

from __future__ import annotations

import json
import re

import asyncio

from urllib.parse import urljoin

from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from google import genai
from google.genai import types
from pydantic import ValidationError

from orbit.config import settings
from orbit.prompts import load_prompt
from orbit.schemas.exhibitor import ExhibitorInput
from orbit.schemas.run import SelectedEvent

LLM_FALLBACK_MODEL = "gemini-2.5-flash"




class ExhibitorFetchError(Exception):
    """
    Levee quand la liste d'exposants ne peut pas etre recuperee, meme apres
    le fallback LLM (Niveau 3 - dernier recours).

    Utilite (Option A, Objectif 4) : permet a l'orchestrateur de renvoyer le
    run au stage AWAITING_SELECTION avec un message clair plutot que de
    planter ou de continuer silencieusement avec des donnees fausses.
    """

    pass

class ExhibitorLinkNotFoundError(ExhibitorFetchError):
    """Etape 2c - aucun lien plausible vers la page exposants (heuristique + LLM ont echoue)."""
    pass



async def _render_page(url: str, timeout_ms: int = 20000) -> str:
    """
    Etape 1 et Etape 3 (Objectif 8) - charge une page avec un navigateur
    headless et retourne le HTML final APRES execution du JavaScript.

    Meme fonction utilisee pour la homepage et pour la page exposants
    localisee ensuite - un seul chemin de code, coherent avec la strategie
    unifiee (voir orbit-semaine2-guide.md, Objectif 8). Remplace _fetch_html
    (httpx), qui ne rendait pas le JS et echouait donc silencieusement sur
    les sites dynamiques (cas embedded-world.eu, hannovermesse.de).
    """
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            html = await page.content()
            await browser.close()
            return html
    except PlaywrightTimeoutError as exc:
        raise ExhibitorFetchError(
            f"Timeout lors du chargement de {url} (page trop lente ou inaccessible)."
        ) from exc
    except Exception as exc:
        raise ExhibitorFetchError(
            f"Impossible de charger {url} avec le navigateur: {exc}"
        ) from exc


_EXHIBITOR_KEYWORDS = [
    "exhibitor", "exhibitors", "exhibitor list", "exhibitor directory", "find exhibitors",
    "exposant", "exposants", "liste des exposants",
    "aussteller", "ausstellerliste",
    "expositor", "expositores",
    "wystawcy", "lista wystawcow",
    "vystavovatel", "vystavovatele",
]


def _extract_links(html: str, base_url: str) -> list[dict]:
    """Etape 1 (suite) - extrait tous les liens de la page rendue, URL resolues en absolu."""
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True)
        if text:  # ignore les liens sans texte visible (icones, etc.)
            links.append({"text": text, "href": urljoin(base_url, a["href"])})
    return links


def _find_exhibitor_link_heuristic(links: list[dict]) -> str | None:
    """
    Etape 2a (tentee en premier) - filtre par mots-cles multilingues.
    Retourne l'URL si UN SEUL lien correspond clairement. Renvoie None si
    0 ou plusieurs matches - dans les deux cas, la decision est ambigue et
    revient a l'Etape 2b plutot que d'etre tranchee arbitrairement ici.
    """
    matches = [
        link for link in links
        if any(kw in link["text"].lower() or kw in link["href"].lower() for kw in _EXHIBITOR_KEYWORDS)
    ]
    return matches[0]["href"] if len(matches) == 1 else None


_LINK_CHOICE_SCHEMA = {
    "type": "OBJECT",
    "properties": {"chosen_href": {"type": "STRING", "nullable": True}},
    "required": ["chosen_href"],
}


async def _find_exhibitor_link_llm(links: list[dict]) -> str | None:
    """
    Etape 2b (secours UNIQUEMENT) - n'est appelee que si l'heuristique n'a
    pas tranche. Le LLM choisit exclusivement parmi les liens reellement
    extraits (response_schema natif, pas de google_search donc pas de
    contrainte d'incompatibilite comme pour le Scout).
    """
    if not settings.gemini_api_key or not links:
        return None

    system_prompt = load_prompt("analyst_link_finder", version="v1")
    links_text = "\n".join(f"{i}: [{l['text']}]({l['href']})" for i, l in enumerate(links))

    client = genai.Client(api_key=settings.gemini_api_key)
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        response_mime_type="application/json",
        response_schema=_LINK_CHOICE_SCHEMA,
    )

    try:
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=LLM_FALLBACK_MODEL,
            contents=links_text,
            config=config,
        )
        result = json.loads(response.text)
    except Exception:
        return None

    chosen = result.get("chosen_href")
    # Securite : verifie que le LLM a bien choisi une URL de la liste fournie
    # (response_schema garantit le FORMAT, pas que la valeur en fasse partie).
    valid_hrefs = {link["href"] for link in links}
    return chosen if chosen in valid_hrefs else None


async def _locate_exhibitor_page(homepage_html: str, homepage_url: str) -> str:
    """Etape 2 complete : 2a -> 2b (si besoin) -> 2c (echec si rien ne ressort)."""
    links = _extract_links(homepage_html, homepage_url)

    target = _find_exhibitor_link_heuristic(links)
    if target is None:
        target = await _find_exhibitor_link_llm(links)

    if target is None:
        raise ExhibitorLinkNotFoundError(
            f"Aucune page d'exposants localisee depuis {homepage_url} - "
            "ni l'heuristique par mots-cles ni le LLM de secours n'ont trouve "
            "de lien plausible parmi les liens reels de la page."
        )
    return target
