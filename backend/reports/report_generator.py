"""Enterprise Report Generation Engine for Phase 8.

Supports Formats:
- PDF (via ReportLab)
- DOCX (via python-docx)
- Excel (via openpyxl)
- PPTX (via python-pptx)

Supports Report Types:
- Executive Summary
- Analytics Report
- Forecast Report
- Recommendations Report

Outputs standard format:
{
  "report_id": "rep_102",
  "file_url": "/reports/rep_102.pdf"
}
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = Path("data/reports")


class ReportGenerator:
    """Multi-format enterprise report generator."""

    def __init__(self, output_dir: Path | str | None = None) -> None:
        self.output_dir = Path(output_dir or DEFAULT_OUTPUT_DIR)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        report_type: str,
        format_type: str = "pdf",
        title: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate report in requested format and return file descriptor."""
        clean_type = report_type.lower().replace(" ", "_")
        clean_format = format_type.lower().replace(".", "").strip()
        if clean_format == "excel":
            clean_format = "xlsx"

        report_id = f"rep_{uuid.uuid4().hex[:8]}"
        filename = f"{report_id}.{clean_format}"
        file_path = self.output_dir / filename

        report_title = title or clean_type.replace("_", " ").title()
        report_data = data if data is not None else self._get_default_report_data(clean_type)
        # Any chart image is generated from supplied computed observations only.
        chart_image = None
        if report_data.get("chart"):
            import io
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_agg import FigureCanvasAgg
            points = report_data["chart"]
            figure = Figure(figsize=(7, 3.5), layout="constrained")
            FigureCanvasAgg(figure)
            axis = figure.subplots()
            axis.bar([str(p["label"]) for p in points], [float(p["value"]) for p in points], color="#9ab52f")
            axis.set_ylabel(report_data.get("chart_label", "Source units"))
            axis.tick_params(axis="x", labelrotation=35)
            chart_image = io.BytesIO()
            figure.savefig(chart_image, format="png", dpi=140)
            chart_image.seek(0)
        report_data = {**report_data, "_chart_image": chart_image}

        if clean_format == "pdf":
            self._generate_pdf(file_path, report_title, clean_type, report_data)
        elif clean_format == "docx":
            self._generate_docx(file_path, report_title, clean_type, report_data)
        elif clean_format == "xlsx":
            self._generate_excel(file_path, report_title, clean_type, report_data)
        elif clean_format == "pptx":
            self._generate_pptx(file_path, report_title, clean_type, report_data)
        else:
            raise ValueError(f"Unsupported report format: {format_type}")

        file_url = f"/reports/{filename}"

        return {
            "report_id": report_id,
            "file_url": file_url,
            "file_path": str(file_path),
            "format": clean_format,
            "report_type": clean_type,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _get_default_report_data(self, report_type: str) -> dict[str, Any]:
        """Provide default structured content for each report type."""
        return {"summary": "No source-backed analysis was supplied.", "kpis": {}, "insights": [], "action_items": []}

    def _generate_pdf(
        self, path: Path, title: str, report_type: str, data: dict[str, Any]
    ) -> None:
        """Generate PDF report using ReportLab."""
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        doc = SimpleDocTemplate(str(path), pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
        styles = getSampleStyleSheet()
        from xml.sax.saxutils import escape
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from matplotlib import get_data_path
        font_path = Path(get_data_path()) / "fonts/ttf/DejaVuSans.ttf"
        pdfmetrics.registerFont(TTFont("ReportUnicode", str(font_path)))
        for style in styles.byName.values(): style.fontName = "ReportUnicode"
        elements = []

        # Title
        title_style = ParagraphStyle("ReportTitle", parent=styles["Heading1"], fontSize=20, leading=24, textColor=colors.HexColor("#1e293b"))
        elements.append(Paragraph(escape(title), title_style))
        elements.append(Spacer(1, 10))

        # Metadata
        meta_style = ParagraphStyle("Meta", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#64748b"))
        elements.append(Paragraph(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')} | Type: {report_type.upper()}", meta_style))
        elements.append(Spacer(1, 15))

        # Executive Summary
        h2_style = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=14, leading=18, textColor=colors.HexColor("#0f172a"))
        body_style = ParagraphStyle("Body", parent=styles["Normal"], fontSize=10, leading=14, textColor=colors.HexColor("#334155"))
        elements.append(Paragraph("Executive Overview", h2_style))
        elements.append(Spacer(1, 6))
        elements.append(Paragraph(escape(data.get("summary", "")), body_style))
        elements.append(Spacer(1, 15))

        # KPIs Table
        kpis = data.get("kpis", {})
        if kpis:
            elements.append(Paragraph("Key Metrics", h2_style))
            elements.append(Spacer(1, 6))
            table_data = [["Metric", "Value"]]
            for k, v in kpis.items():
                table_data.append([str(k), str(v)])

            t = Table(table_data, colWidths=[280, 200])
            t.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563eb")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("FONTNAME", (0, 0), (-1, -1), "ReportUnicode"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ])
            )
            elements.append(t)
            elements.append(Spacer(1, 15))

        # Insights & Actions
        insights = data.get("insights", [])
        if insights:
            elements.append(Paragraph("Strategic Insights", h2_style))
            elements.append(Spacer(1, 6))
            for item in insights:
                elements.append(Paragraph(f"• {item}", body_style))
            elements.append(Spacer(1, 15))

        actions = data.get("action_items", [])
        if actions:
            elements.append(Paragraph("Recommended Next Steps", h2_style))
            elements.append(Spacer(1, 6))
            for action in actions:
                elements.append(Paragraph(f"✓ {action}", body_style))

        if data.get("_chart_image"):
            from reportlab.platypus import Image
            elements.append(Image(data["_chart_image"], width=480, height=240))
        doc.build(elements)

    def _generate_docx(
        self, path: Path, title: str, report_type: str, data: dict[str, Any]
    ) -> None:
        """Generate DOCX document."""
        import docx

        doc = docx.Document()
        doc.add_heading(title, level=0)
        doc.add_paragraph(f"Report Type: {report_type.upper()} | Generated: {datetime.now(timezone.utc).isoformat()}")

        doc.add_heading("Executive Summary", level=1)
        doc.add_paragraph(data.get("summary", ""))

        kpis = data.get("kpis", {})
        if kpis:
            doc.add_heading("Key Performance Indicators", level=1)
            table = doc.add_table(rows=1, cols=2)
            hdr_cells = table.rows[0].cells
            hdr_cells[0].text = "Metric"
            hdr_cells[1].text = "Value"
            for k, v in kpis.items():
                row_cells = table.add_row().cells
                row_cells[0].text = str(k)
                row_cells[1].text = str(v)

        insights = data.get("insights", [])
        if insights:
            doc.add_heading("Key Insights", level=1)
            for item in insights:
                doc.add_paragraph(item, style="List Bullet")

        actions = data.get("action_items", [])
        if actions:
            doc.add_heading("Action Plan", level=1)
            for action in actions:
                doc.add_paragraph(action, style="List Bullet")

        if data.get("_chart_image"):
            from docx.shared import Inches
            doc.add_picture(data["_chart_image"], width=Inches(6))
        doc.save(str(path))

    def _generate_excel(
        self, path: Path, title: str, report_type: str, data: dict[str, Any]
    ) -> None:
        """Generate Excel workbook with styled summary."""
        import openpyxl
        from openpyxl.styles import Font, PatternFill

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Executive Summary"

        # Title
        ws["A1"] = title
        ws["A1"].font = Font(size=16, bold=True, color="1E293B")
        ws["A2"] = f"Report Type: {report_type.upper()} | Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}"

        # Summary
        ws["A4"] = "Overview"
        ws["A4"].font = Font(bold=True)
        ws["A5"] = data.get("summary", "")

        # KPIs
        kpis = data.get("kpis", {})
        ws["A7"] = "Metric"
        ws["B7"] = "Value"
        ws["A7"].font = Font(bold=True, color="FFFFFF")
        ws["B7"].font = Font(bold=True, color="FFFFFF")
        ws["A7"].fill = PatternFill("solid", fgColor="2563EB")
        ws["B7"].fill = PatternFill("solid", fgColor="2563EB")

        row = 8
        for k, v in kpis.items():
            ws.cell(row=row, column=1, value=str(k))
            ws.cell(row=row, column=2, value=str(v))
            row += 1

        # Insights
        row += 1
        ws.cell(row=row, column=1, value="Strategic Insights").font = Font(bold=True)
        row += 1
        for item in data.get("insights", []):
            ws.cell(row=row, column=1, value=f"- {item}")
            row += 1

        if data.get("chart"):
            from openpyxl.chart import BarChart, Reference
            chart_sheet = wb.create_sheet("Chart evidence")
            chart_sheet.append(["Dimension", "Value"])
            for point in data["chart"]: chart_sheet.append([str(point["label"]), float(point["value"])])
            chart = BarChart(); chart.title = data.get("chart_label", "Source units")
            chart.add_data(Reference(chart_sheet, min_col=2, min_row=1, max_row=chart_sheet.max_row), titles_from_data=True)
            chart.set_categories(Reference(chart_sheet, min_col=1, min_row=2, max_row=chart_sheet.max_row))
            chart_sheet.add_chart(chart, "D2")
        # Source-provided strings are always literal cells, never formulas.
        for sheet in wb:
            for row_cells in sheet:
                for cell in row_cells:
                    if isinstance(cell.value, str): cell.data_type = "s"
        ws.column_dimensions["A"].width = 60; ws.column_dimensions["B"].width = 30
        wb.save(str(path))

    def _generate_pptx(
        self, path: Path, title: str, report_type: str, data: dict[str, Any]
    ) -> None:
        """Generate PowerPoint presentation."""
        from pptx import Presentation
        from pptx.util import Inches, Pt

        prs = Presentation()

        # Slide 1: Title
        title_slide_layout = prs.slide_layouts[0]
        slide = prs.slides.add_slide(title_slide_layout)
        slide.shapes.title.text = title
        slide.placeholders[1].text = f"Enterprise Briefing\n{report_type.replace('_', ' ').title()}"

        # Slide 2: Overview & KPIs
        bullet_slide_layout = prs.slide_layouts[1]
        slide2 = prs.slides.add_slide(bullet_slide_layout)
        slide2.shapes.title.text = "Overview & Key Metrics"
        tf2 = slide2.placeholders[1].text_frame
        tf2.text = data.get("summary", "")

        for k, v in data.get("kpis", {}).items():
            p = tf2.add_paragraph()
            p.text = f"{k}: {v}"
            p.level = 1

        # Slide 3: Insights & Next Steps
        slide3 = prs.slides.add_slide(bullet_slide_layout)
        slide3.shapes.title.text = "Strategic Insights & Next Steps"
        tf3 = slide3.placeholders[1].text_frame
        tf3.text = "Key Takeaways:"
        for item in data.get("insights", []):
            p = tf3.add_paragraph()
            p.text = item
            p.level = 1

        if data.get("_chart_image"):
            slide = prs.slides.add_slide(prs.slide_layouts[5])
            slide.shapes.title.text = data.get("chart_label", "Source observations")
            slide.shapes.add_picture(data["_chart_image"], Inches(1), Inches(1.5), width=Inches(8))
        prs.save(str(path))


# Global report generator singleton
report_generator = ReportGenerator()
