"""PDF round trip: tailored text -> generated PDF -> parsed text.

This is the path every application's resume takes, so it is tested end to end
on real files rather than by mocking reportlab and pymupdf.
"""
import pytest

from src.documents.pdf_generator import save_pdf
from src.documents.resume_parser import parse_resume

RESUME = """JANE DOE
jane@example.com

EXPERIENCE:
Software Engineer, Acme Corp
Built a billing service handling 2M requests/day

EDUCATION:
B.S. Computer Science
"""


def test_generated_pdf_round_trips_its_text(tmp_path):
    path = save_pdf(RESUME, str(tmp_path / "resume.pdf"))
    text = parse_resume(path)
    for fragment in ["JANE DOE", "Software Engineer, Acme Corp", "2M requests/day", "B.S. Computer Science"]:
        assert fragment in text


def test_markup_characters_are_escaped_not_interpreted(tmp_path):
    # ReportLab parses Paragraph text as XML. An unescaped "<" in a resume
    # ("C++ & <Rust>") would either crash the build or silently drop text.
    path = save_pdf("Skills: C++ & <Rust> & Go", str(tmp_path / "r.pdf"))
    text = parse_resume(path)
    assert "C++ & <Rust> & Go" in text


def test_output_directory_is_created(tmp_path):
    target = tmp_path / "nested" / "deeper" / "resume.pdf"
    save_pdf(RESUME, str(target))
    assert target.exists()


def test_missing_resume_raises_a_clear_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="Resume not found"):
        parse_resume(str(tmp_path / "nope.pdf"))


def test_a_pdf_with_no_extractable_text_is_rejected(tmp_path):
    # A scanned-image resume yields no text. Tailoring an empty string would
    # send the model nothing to work from, so fail here instead.
    path = save_pdf("\n\n\n", str(tmp_path / "blank.pdf"))
    with pytest.raises(ValueError, match="Could not extract text"):
        parse_resume(path)
