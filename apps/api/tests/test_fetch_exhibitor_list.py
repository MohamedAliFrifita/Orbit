"""
Test du parsing de fetch_exhibitor_list.

Utilite : on teste le parsing contre une fixture HTML locale plutot que
contre le vrai site a chaque `pytest -v` - plus rapide, plus fiable
(pas de dependance reseau), et ne casse pas si le vrai site change entre-temps
(voir orbit-coding-guide.md §8, Objectif 7).
"""

from pathlib import Path

from orbit.tools.fetch_exhibitor_list import _parse_exhibitors_static

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sepem_douai_exhibitors.html"


def _load_fixture_html() -> str:
    return FIXTURE_PATH.read_text(encoding="utf-8")


def test_parses_all_known_exhibitors_from_fixture():
    html = _load_fixture_html()
    exhibitors = _parse_exhibitors_static(html)

    # 10 exposants dans la fixture (voir tests/fixtures/sepem_douai_exhibitors.html)
    assert len(exhibitors) == 10


def test_parses_name_and_booth_correctly():
    html = _load_fixture_html()
    exhibitors = _parse_exhibitors_static(html)

    faro = next(e for e in exhibitors if "FARO" in e.name)
    assert faro.name == "FARO FRANCE"
    assert "A50" in faro.booth


def test_handles_missing_stand_number_gracefully():
    """Certains exposants reels n'ont pas de numero de stand (ex: 'AMITEC...Stand' sans code)."""
    html = _load_fixture_html()
    exhibitors = _parse_exhibitors_static(html)

    amitec = next(e for e in exhibitors if "AMITEC" in e.name)
    assert amitec.name == "AMITEC"
    # le stand peut etre vide, mais ca ne doit pas faire planter le parsing


def test_handles_multiple_stand_numbers():
    """Certains exposants ont plusieurs stands (ex: 'KIO SOFTWARE...Stand C104,B55')."""
    html = _load_fixture_html()
    exhibitors = _parse_exhibitors_static(html)

    kio = next(e for e in exhibitors if "KIO" in e.name)
    assert "C104" in kio.booth
    assert "B55" in kio.booth


def test_returns_empty_list_on_unparseable_html():
    """Une page sans le pattern attendu doit renvoyer une liste vide,
    pas planter - c'est ce vide que fetch_exhibitor_list() interprete ensuite
    comme une erreur a remonter (voir ExhibitorFetchError)."""
    exhibitors = _parse_exhibitors_static("<html><body><p>Rien a voir ici</p></body></html>")
    assert exhibitors == []


# --- Tests du pipeline a 3 niveaux (Niveau 2 : fallback LLM, Niveau 3 : echec final) ---
# Utilite : jamais de vrai appel reseau/LLM dans ces tests (voir orbit-contexte-semaine2.md
# §5 "strategie de test") - tout est mocke.

import pytest

from orbit.schemas.run import SelectedEvent
from orbit.tools.fetch_exhibitor_list import ExhibitorFetchError, fetch_exhibitor_list


def _make_event(source_url: str) -> SelectedEvent:
    return SelectedEvent(name="Salon Test", dates="2026-01-01", location="Paris", exhibitor_count=0, source_url=source_url)


async def test_falls_back_to_llm_when_static_parsing_finds_nothing(monkeypatch):
    """Niveau 1 echoue (HTML sans le pattern SEPEM) -> Niveau 2 (LLM) doit etre tente."""
    import orbit.tools.fetch_exhibitor_list as mod

    async def fake_fetch_html(url):
        return "<html><body><div>Structure inconnue, pas de pattern SEPEM ici</div></body></html>"

    async def fake_llm_parse(html, source_url):
        from orbit.schemas.exhibitor import ExhibitorInput
        return [ExhibitorInput(id="llm_0000", name="Exposant Trouve Par LLM", raw_description="test")]

    monkeypatch.setattr(mod, "_fetch_html", fake_fetch_html)
    monkeypatch.setattr(mod, "_parse_exhibitors_llm", fake_llm_parse)

    exhibitors = await fetch_exhibitor_list(_make_event("https://exemple.com/exposants"))

    assert len(exhibitors) == 1
    assert exhibitors[0].name == "Exposant Trouve Par LLM"


async def test_does_not_call_llm_when_static_parsing_succeeds(monkeypatch):
    """Utilite : verifie que le Niveau 2 (couteux) n'est PAS declenche quand le
    Niveau 1 (gratuit) suffit deja - important pour le controle de cout/quota."""
    import orbit.tools.fetch_exhibitor_list as mod

    html = (Path(__file__).parent / "fixtures" / "sepem_douai_exhibitors.html").read_text(encoding="utf-8")

    async def fake_fetch_html(url):
        return html

    llm_call_count = {"n": 0}

    async def fake_llm_parse(html, source_url):
        llm_call_count["n"] += 1
        return []

    monkeypatch.setattr(mod, "_fetch_html", fake_fetch_html)
    monkeypatch.setattr(mod, "_parse_exhibitors_llm", fake_llm_parse)

    exhibitors = await fetch_exhibitor_list(_make_event("https://sepem-test.com"))

    assert len(exhibitors) == 10  # trouve par le Niveau 1
    assert llm_call_count["n"] == 0  # Niveau 2 jamais appele


async def test_raises_after_both_levels_fail(monkeypatch):
    """Niveau 1 et Niveau 2 echouent tous les deux -> ExhibitorFetchError (Niveau 3),
    typiquement le signe d'un site a rendu JavaScript (voir docstring du module)."""
    import orbit.tools.fetch_exhibitor_list as mod

    async def fake_fetch_html(url):
        return "<html><body><div id='app'></div></body></html>"  # ex: page JS vide

    async def fake_llm_parse(html, source_url):
        return []

    monkeypatch.setattr(mod, "_fetch_html", fake_fetch_html)
    monkeypatch.setattr(mod, "_parse_exhibitors_llm", fake_llm_parse)

    with pytest.raises(ExhibitorFetchError):
        await fetch_exhibitor_list(_make_event("https://site-js.com"))
