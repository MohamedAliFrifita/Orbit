import pytest

pytest.importorskip("playwright")  # skip proprement si Playwright n'est pas installe

from orbit.tools.fetch_exhibitor_list import _render_page


@pytest.mark.playwright
async def test_render_page_executes_javascript(tmp_path):
    """
    Test d'integration leger : verifie que _render_page execute reellement le
    JS, via un fichier local (file://) - aucune dependance reseau externe,
    mais necessite les binaires Playwright installes (playwright install chromium).
    """
    html_file = tmp_path / "js_page.html"
    html_file.write_text(
        "<html><body><div id='target'></div>"
        "<script>document.getElementById('target').textContent = 'Rendu OK';</script>"
        "</body></html>"
    )
    rendered = await _render_page(html_file.as_uri())
    assert "Rendu OK" in rendered