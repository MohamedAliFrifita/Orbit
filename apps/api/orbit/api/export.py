"""Export PDF de l'itinéraire — généré à la demande depuis l'historique."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from jinja2 import DictLoader, Environment

from orbit.api.deps import get_current_user
from orbit.db.models import User

router = APIRouter(tags=["export"])

# Template HTML Jinja2 embarqué (WeasyPrint convertit HTML→PDF)
_HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<style>
  body { font-family: Arial, sans-serif; font-size: 12px; margin: 40px; }
  h1 { color: #2c3e50; border-bottom: 2px solid #2c3e50; }
  h2 { color: #34495e; margin-top: 24px; }
  table { width: 100%; border-collapse: collapse; margin-top: 12px; }
  th { background: #2c3e50; color: white; padding: 8px; text-align: left; }
  td { padding: 7px 8px; border-bottom: 1px solid #ddd; }
  tr:nth-child(even) { background: #f8f9fa; }
  .badge-warning { background: #f39c12; color: white; padding: 2px 8px;
                   border-radius: 4px; font-size: 10px; }
  .meta { color: #7f8c8d; font-size: 10px; margin-top: 40px; }
</style>
</head>
<body>
<h1>Itinéraire de visite — {{ event_name }}</h1>
<p>{{ event_dates }} · {{ event_location }}</p>
{% if low_confidence %}
<p><span class="badge-warning">⚠ Résultat à faible confiance</span>
Certains stages ont été forcés PASS : {{ low_confidence_stages | join(', ') }}</p>
{% endif %}

<h2>Profil ICP</h2>
<p>{{ icp_profile }}</p>
<p><strong>Objectifs :</strong> {{ objectives }}</p>

<h2>Itinéraire ({{ stops | length }} stops)</h2>
<table>
  <tr>
    <th>#</th><th>Exposant</th><th>Stand</th>
    <th>Créneau</th><th>Objectif</th><th>Justification</th>
  </tr>
  {% for s in stops %}
  <tr>
    <td>{{ s.order }}</td>
    <td>{{ s.exhibitor_name }}</td>
    <td>{{ s.booth or '—' }}</td>
    <td>{{ s.time_slot or '—' }}</td>
    <td>{{ s.objective }}</td>
    <td>{{ s.justification }}</td>
  </tr>
  {% endfor %}
</table>

<div class="meta">
  Généré par ORBIT · {{ generated_at }}
</div>
</body>
</html>
"""


@router.get("/runs/{run_id}/export/pdf")
async def export_pdf(
    run_id: str,
    current_user: User = Depends(get_current_user),
) -> Response:
    """Génère et retourne le PDF de l'itinéraire d'un run DONE."""
    from orbit.api.stream import _RUNS  # store en mémoire (remplacer par DB)
    from orbit.schemas.run import RunStage
    from datetime import datetime

    state = _RUNS.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Run introuvable")
    if state.client_id != current_user.id:
        raise HTTPException(status_code=404, detail="Run introuvable")
    if state.stage != RunStage.DONE:
        raise HTTPException(status_code=409, detail="Le run n'est pas encore terminé")

    env = Environment(loader=DictLoader({"template.html": _HTML_TEMPLATE}))
    template = env.get_template("template.html")

    ev = state.selected_event
    html_content = template.render(
        event_name=ev.name if ev else "—",
        event_dates=ev.dates if ev else "—",
        event_location=ev.location if ev else "—",
        low_confidence=state.low_confidence,
        low_confidence_stages=state.low_confidence_stages,
        icp_profile=state.input.icp.target_client_profile,
        objectives=", ".join(o.value for o in state.input.icp.objectives),
        stops=state.itinerary,
        generated_at=datetime.now().strftime("%d/%m/%Y %H:%M"),
    )

    try:
        from weasyprint import HTML
        pdf_bytes = HTML(string=html_content).write_pdf()
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="WeasyPrint non installé — `pip install weasyprint`",
        )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="orbit-{run_id[:8]}.pdf"'},
    )