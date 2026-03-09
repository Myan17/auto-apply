"""Generate PDF documents from plain text."""

import re
from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer


def _clean(text: str) -> str:
    """Escape special ReportLab XML characters."""
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    return text


def _build_styles():
    styles = getSampleStyleSheet()

    normal = ParagraphStyle(
        "NormalCustom",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        spaceAfter=4,
    )
    heading = ParagraphStyle(
        "HeadingCustom",
        parent=styles["Heading2"],
        fontSize=11,
        leading=16,
        spaceBefore=10,
        spaceAfter=4,
        textColor=colors.HexColor("#1a1a1a"),
    )
    return normal, heading


def save_pdf(text: str, output_path: str) -> str:
    """Render plain text as a PDF. Returns the output path."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        leftMargin=0.8 * inch,
        rightMargin=0.8 * inch,
        topMargin=0.8 * inch,
        bottomMargin=0.8 * inch,
    )

    normal_style, heading_style = _build_styles()
    story = []

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            story.append(Spacer(1, 6))
            continue

        # Detect section headers: all-caps or ends with colon, short lines
        if (stripped.isupper() or stripped.endswith(":")) and len(stripped) < 60:
            story.append(Paragraph(_clean(stripped), heading_style))
        else:
            story.append(Paragraph(_clean(stripped), normal_style))

    doc.build(story)
    return output_path
