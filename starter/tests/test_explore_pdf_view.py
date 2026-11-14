import pymupdf
import pytest

from src.explore.pdf_view import NOT_FOUND_NOTE, render_page

LONG = "Dong B gamma delta epsilon zeta eta theta"


@pytest.fixture
def pdf(tmp_path):
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Dong A alpha beta", fontsize=12)
    page.insert_text((72, 130), LONG, fontsize=12)
    path = tmp_path / "t.pdf"
    doc.save(path)
    return path


def test_highlight_found_changes_image_and_note_empty(pdf):
    plain, _ = render_page(pdf, 1, None)
    marked, note = render_page(pdf, 1, "Dong A alpha beta Dong B gamma delta epsilon zeta eta theta")
    assert plain[:4] == b"\x89PNG" and marked[:4] == b"\x89PNG"
    assert marked != plain and note == ""


def test_highlight_text_not_on_page(pdf):
    plain, _ = render_page(pdf, 1, None)
    png, note = render_page(pdf, 1, "chuoi nay khong he co tren trang pdf nay dau")
    assert png[:4] == b"\x89PNG" and note == NOT_FOUND_NOTE and png == plain


def test_none_highlight_ok(pdf):
    png, note = render_page(pdf, 1, None)
    assert png[:4] == b"\x89PNG" and note == ""


def test_chunk_continuing_onto_next_page_notes_it(pdf):
    png, note = render_page(pdf, 1, LONG + " iota kappa lambda mu nu xi omicron pi")
    assert "trang sau" in note and png[:4] == b"\x89PNG"


def test_page_out_of_range_does_not_raise(pdf):
    png, note = render_page(pdf, 99, "x")
    assert png == b"" and "không có trang" in note
