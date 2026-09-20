"""Export PDF de l'itinéraire — généré avec ReportLab (100% compatible Windows/Linux)."""

from __future__ import annotations

import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from orbit.api.deps import get_current_user
from orbit.db.models import User

router = APIRouter(tags=["export"])


@router.get("/runs/{run_id}/export/pdf")
async def export_pdf(
    run_id: str,
    current_user: User = Depends(get_current_user),
) -> Response:
    """Génère et retourne le PDF de l'itinéraire d'un run DONE."""
    from orbit.api.stream import _RUNS
    from orbit.schemas.run import RunStage

    state = _RUNS.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Run introuvable")
    if state.client_id != current_user.id:
        raise HTTPException(status_code=404, detail="Run introuvable")
    if state.stage != RunStage.DONE:
        raise HTTPException(status_code=409, detail="Le run n'est pas encore terminé")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=30,
        leftMargin=30,
        topMargin=30,
        bottomMargin=30,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#1e293b"),
        spaceAfter=6,
    )
    sub_style = ParagraphStyle(
        "DocSubtitle",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#64748b"),
        spaceAfter=14,
    )
    section_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontSize=13,
        leading=16,
        textColor=colors.HexColor("#0f172a"),
        spaceBefore=10,
        spaceAfter=6,
    )
    cell_style = ParagraphStyle(
        "CellText",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#334155"),
    )
    header_style = ParagraphStyle(
        "HeaderCell",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        fontName="Helvetica-Bold",
        textColor=colors.white,
    )

    elements = []

    # En-tête
    ev = state.selected_event
    event_title = ev.name if ev else "Événement Professionnel"
    elements.append(Paragraph(f"Itinéraire de visite — {event_title}", title_style))

    dates_loc = f"{ev.dates if ev else ''} · {ev.location if ev else ''}"
    elements.append(Paragraph(dates_loc, sub_style))

    # Avertissement si low_confidence
    if state.low_confidence:
        alert_style = ParagraphStyle(
            "Alert",
            parent=styles["Normal"],
            fontSize=8,
            textColor=colors.HexColor("#b45309"),
        )
        elements.append(
            Paragraph(
                "⚠ <b>Note :</b> Résultat validé avec tolérance sur certains critères.",
                alert_style,
            )
        )
        elements.append(Spacer(1, 8))

    # Profil ICP
    elements.append(Paragraph("Contexte & Objectifs", section_style))
    icp_text = (
        f"<b>Cible :</b> {state.input.icp.target_client_profile}<br/>"
        f"<b>Objectifs :</b> {', '.join(o.value for o in state.input.icp.objectives)}"
    )
    elements.append(Paragraph(icp_text, cell_style))
    elements.append(Spacer(1, 14))

    # Tableau des stops
    stops = state.itinerary or []
    elements.append(
        Paragraph(f"Itinéraire de visite ({len(stops)} arrêts planifiés)", section_style)
    )

    table_data = [
        [
            Paragraph("#", header_style),
            Paragraph("Exposant", header_style),
            Paragraph("Stand", header_style),
            Paragraph("Créneau", header_style),
            Paragraph("Objectif", header_style),
            Paragraph("Justification", header_style),
        ]
    ]

    for s in stops:
        order_val = str(getattr(s, "order", "") or (s.get("order") if isinstance(s, dict) else ""))
        name_val = str(getattr(s, "exhibitor_name", "") or (s.get("exhibitor_name") if isinstance(s, dict) else ""))
        booth_val = str(getattr(s, "booth", "") or (s.get("booth") if isinstance(s, dict) else "") or "—")
        slot_val = str(getattr(s, "time_slot", "") or (s.get("time_slot") if isinstance(s, dict) else "") or "—")
        obj_val = str(getattr(s, "objective", "") or (s.get("objective") if isinstance(s, dict) else ""))
        just_val = str(getattr(s, "justification", "") or (s.get("justification") if isinstance(s, dict) else ""))

        table_data.append([
            Paragraph(order_val, cell_style),
            Paragraph(f"<b>{name_val}</b>", cell_style),
            Paragraph(booth_val, cell_style),
            Paragraph(slot_val, cell_style),
            Paragraph(obj_val, cell_style),
            Paragraph(just_val, cell_style),
        ])

    col_widths = [20, 95, 45, 65, 120, 190]
    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ])
    )
    elements.append(t)
    elements.append(Spacer(1, 20))

    # Footer
    footer_text = f"Généré par ORBIT · {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    elements.append(Paragraph(footer_text, sub_style))

    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="orbit-{run_id[:8]}.pdf"'},
    )