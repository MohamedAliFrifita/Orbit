"""
Test du parsing de fetch_exhibitor_list.

Utilite : on teste le parsing contre une fixture HTML locale plutot que
contre le vrai site a chaque `pytest -v` - plus rapide, plus fiable
(pas de dependance reseau), et ne casse pas si le vrai site change entre-temps
(voir orbit-coding-guide.md §8, Objectif 7).
"""

from pathlib import Path

from orbit.tools.fetch_exhibitor_list import _parse_exhibitors

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sepem_douai_exhibitors.html"


def _load_fixture_html() -> str:
    return FIXTURE_PATH.read_text(encoding="utf-8")


def test_parses_all_known_exhibitors_from_fixture():
    html = _load_fixture_html()
    exhibitors = _parse_exhibitors(html)

    # 10 exposants dans la fixture (voir tests/fixtures/sepem_douai_exhibitors.html)
    assert len(exhibitors) == 10


def test_parses_name_and_booth_correctly():
    html = _load_fixture_html()
    exhibitors = _parse_exhibitors(html)

    faro = next(e for e in exhibitors if "FARO" in e.name)
    assert faro.name == "FARO FRANCE"
    assert "A50" in faro.booth


def test_handles_missing_stand_number_gracefully():
    """Certains exposants reels n'ont pas de numero de stand (ex: 'AMITEC...Stand' sans code)."""
    html = _load_fixture_html()
    exhibitors = _parse_exhibitors(html)

    amitec = next(e for e in exhibitors if "AMITEC" in e.name)
    assert amitec.name == "AMITEC"


def test_handles_multiple_stand_numbers():
    """Certains exposants ont plusieurs stands (ex: 'KIO SOFTWARE...Stand C104,B55')."""
    html = _load_fixture_html()
    exhibitors = _parse_exhibitors(html)

    kio = next(e for e in exhibitors if "KIO" in e.name)
    assert "C104" in kio.booth
    assert "B55" in kio.booth


def test_returns_empty_list_on_unparseable_html():
    """Une page sans le pattern attendu doit renvoyer une liste vide,
    pas planter - c'est ce vide que fetch_exhibitor_list() interprete ensuite
    comme une erreur a remonter (voir ExhibitorFetchError)."""
    exhibitors = _parse_exhibitors("<html><body><p>Rien a voir ici</p></body></html>")
    assert exhibitors == []