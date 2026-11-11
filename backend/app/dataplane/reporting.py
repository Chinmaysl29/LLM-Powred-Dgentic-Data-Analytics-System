"""Render only bounded persisted evidence; no recomputation or invented narrative."""
from io import BytesIO
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle


def render_pdf(identity, evidence):
    output = BytesIO()
    document = SimpleDocTemplate(output)
    styles = getSampleStyleSheet()
    parts = [Paragraph("Verified aggregate report", styles["Title"]),
             Paragraph("Evidence: "+escape(identity), styles["Normal"])]
    for key in ("snapshot_id", "semantic_id", "snapshot_hash", "query_hash", "engine", "engine_version",
                "input_rows", "result_rows", "elapsed_ms", "result_hash", 'contract_version',
                'definition_id', 'definition_version', 'definition_hash', 'source_version', 'coverage',
                'snapshot_guarantee', 'business_date', 'validation_status', 'completed_at', 'workflow_id', 'workflow_version'):
        if key in evidence:
            parts.append(Paragraph(escape(f"{key}: {evidence[key]}"), styles["Normal"]))
    if evidence.get('definition_context'):
        for key, value in evidence['definition_context'].items():
            parts.append(Paragraph(escape(f'{key}: {value}'), styles['Normal']))
        for finding in evidence.get('quality_checks', []):
            parts.append(Paragraph(escape(f"Check {finding['field']}: {finding['status']}; "
                f"observed={finding['observed']}; coverage={finding['coverage']}; impact={finding['impact']}"), styles['Normal']))
        plan = evidence.get('plan', {})
        parts.append(Paragraph(escape('Dimensions: ' + str(plan.get('dimensions', []))), styles['Normal']))
        for item in plan.get('filters', []):
            parts.append(Paragraph(escape(f"Filter: {item['column']} {item['operator']} [redacted literal]"), styles['Normal']))
        if evidence.get('time_window'):
            parts.append(Paragraph(escape('Resolved time window (end exclusive): ' + str(evidence['time_window'])), styles['Normal']))
    else:
        parts.append(Paragraph('Company definition and review provenance unavailable for this historical or exploratory report.', styles['Normal']))
    parts.append(Spacer(1, 14))
    rows = evidence["rows"]
    if rows:
        columns = list(rows[0])
        data = [[Paragraph(escape(str(c)), styles["Normal"]) for c in columns]]
        data.extend([[Paragraph(escape(str(row.get(c))[:1000]), styles["Normal"]) for c in columns] for row in rows[:100]])
        table = Table(data, repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e7eef5")),
                                   ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        parts.append(table)
    if len(rows) > 100:
        parts.append(Paragraph("First 100 result rows shown. The complete bounded result is stored with the evidence.", styles["Normal"]))
    parts.append(Paragraph("Values come from the recorded engine execution. No business cause is inferred.", styles["Normal"]))
    document.build(parts)
    return output.getvalue()

