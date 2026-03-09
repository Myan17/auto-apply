"""Extract text from a PDF resume."""

from pathlib import Path
import pymupdf  # fitz


def parse_resume(path: str) -> str:
    """Extract clean text from a PDF file."""
    pdf_path = Path(path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"Resume not found: {path}")

    doc = pymupdf.open(str(pdf_path))
    pages = []
    for page in doc:
        pages.append(page.get_text())
    doc.close()

    text = "\n".join(pages).strip()
    if not text:
        raise ValueError(f"Could not extract text from resume: {path}")

    return text
