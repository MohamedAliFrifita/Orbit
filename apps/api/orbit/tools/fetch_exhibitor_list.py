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

from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from google import genai
from google.genai import types
from pydantic import ValidationError

from orbit.config import settings
from orbit.prompts import load_prompt
from orbit.schemas.exhibitor import ExhibitorInput
from orbit.schemas.run import SelectedEvent

SEPEM_DOUAI_URL = "https://douai.sepem-industries.com/content/liste-des-exposants"
LLM_FALLBACK_MODEL = "gemini-2.5-flash"

# Pattern observe sur SEPEM Douai : nom colle directement au lieu + " - Stand " + code
_ENTRY_PATTERN = re.compile(
    r"^(?P<name>.+?)"
    r"(?:(?P<hall>Grand palais|Novaxia bas))?"
    r"\s*-\s*Stand\s*(?P<stand>[A-Za-z0-9,]*)$"
)


class ExhibitorFetchError(Exception):
    """
    Levee quand la liste d'exposants ne peut pas etre recuperee, meme apres
    le fallback LLM (Niveau 3 - dernier recours).

    Utilite (Option A, Objectif 4) : permet a l'orchestrateur de renvoyer le
    run au stage AWAITING_SELECTION avec un message clair plutot que de
    planter ou de continuer silencieusement avec des donnees fausses.
    """

    pass


async def fetch_exhibitor_list(event: SelectedEvent, url: str | None = None) -> list[ExhibitorInput]:
    """Pipeline a 3 niveaux - voir le docstring du module pour le detail de chaque etage."""
    target_url = url or event.source_url or SEPEM_DOUAI_URL

    html = await _fetch_html(target_url)

    # Niveau 1 : parsing statique par regex (gratuit, rapide)
    exhibitors = _parse_exhibitors_static(html)
    if exhibitors:
        return exhibitors

    # Niveau 2 : fallback LLM (coute un appel Gemini)
    exhibitors = await _parse_exhibitors_llm(html, target_url)
    if exhibitors:
        return exhibitors

    # Niveau 3 : dernier recours
    raise ExhibitorFetchError(
        f"Aucun exposant trouve sur {target_url}, ni par parsing statique ni par "
        "extraction LLM - le contenu est probablement genere par JavaScript "
        "(site a rendu dynamique, cas non gere actuellement - voir Playwright "
        "comme prochaine etape si ce cas se confirme)."
    )


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


def _parse_exhibitors_static(html: str) -> list[ExhibitorInput]:
    """Niveau 1 - voir _ENTRY_PATTERN pour le detail du pattern SEPEM Douai."""
    soup = BeautifulSoup(html, "html.parser")
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

        exhibitor_id = f"static_{i:04d}"
        if exhibitor_id in seen_ids:
            continue
        seen_ids.add(exhibitor_id)

        booth = f"{hall} - Stand {stand}".strip(" -") if (hall or stand) else None

        exhibitors.append(
            ExhibitorInput(id=exhibitor_id, name=name, booth=booth, raw_description=text)
        )

    return exhibitors


def _clean_html_to_text(html: str) -> str:
    """
    Utilite (Decision 1) : supprime le bruit (scripts, styles, nav, footer,
    header) avant l'envoi au LLM - economise des tokens sur un quota limite,
    et concentre le signal utile pour l'extraction.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


_EXTRACTION_SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "name": {"type": "STRING"},
            "booth": {"type": "STRING", "nullable": True},
        },
        "required": ["name"],
    },
}


async def _parse_exhibitors_llm(html: str, source_url: str) -> list[ExhibitorInput]:
    """
    Niveau 2 - utilise response_schema natif (Decision 2) : contrairement au
    Scout, cette tache n'a pas besoin de google_search, donc pas de contrainte
    d'incompatibilite - l'API garantit une sortie JSON conforme au schema,
    pas besoin de re-prompt correctif (Decision 3).
    """
    if not settings.gemini_api_key:
        return []

    cleaned_text = _clean_html_to_text(html)
    # Limite de securite pour ne pas exploser le budget de tokens sur une page enorme
    cleaned_text = cleaned_text[:20000]

    system_prompt = load_prompt("analyst", version="v1")
    client = genai.Client(api_key=settings.gemini_api_key)
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        response_mime_type="application/json",
        response_schema=_EXTRACTION_SCHEMA,
    )

    import asyncio

    try:
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=LLM_FALLBACK_MODEL,
            contents=cleaned_text,
            config=config,
        )
    except Exception:
        # Echec de l'appel LLM lui-meme (quota, reseau...) -> on retombe sur
        # le Niveau 3 (ExhibitorFetchError) plutot que de propager une erreur
        # differente ici.
        return []

    try:
        raw_items = json.loads(response.text)
    except (json.JSONDecodeError, TypeError):
        return []

    exhibitors: list[ExhibitorInput] = []
    for i, item in enumerate(raw_items):
        try:
            name = item["name"].strip()
            if not name:
                continue
            exhibitors.append(
                ExhibitorInput(
                    id=f"llm_{i:04d}",
                    name=name,
                    booth=item.get("booth"),
                    raw_description=f"[extrait par LLM depuis {source_url}]",
                )
            )
        except (KeyError, AttributeError, ValidationError):
            continue

    return exhibitors
