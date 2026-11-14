"""Render a PDF page to PNG with a chunk's text highlighted (best effort, never raises on missing text)."""
from pathlib import Path

import pymupdf

from ..evaluation import squash

NOT_FOUND_NOTE = "không định vị được đoạn trên trang"
NEXT_PAGE_NOTE = "đoạn tiếp tục sang trang sau"
PREV_PAGE_NOTE = "đoạn bắt đầu từ trang trước"
_PROBE = 25


def _locate(words: list, chunk_sq: str) -> tuple[int, int, str] | None:
    """(start, end) offsets in the squashed page text covered by the chunk, plus a note; None if absent."""
    page_sq = "".join(squash(w[4]) for w in words)
    if not chunk_sq:
        return None
    i = page_sq.find(chunk_sq)
    if i != -1:
        return i, i + len(chunk_sq), ""
    k = min(_PROBE, len(chunk_sq))
    head, tail = page_sq.find(chunk_sq[:k]), page_sq.rfind(chunk_sq[-k:])
    if head != -1 and tail != -1 and tail + k > head:
        return head, tail + k, ""
    if head != -1:
        return head, len(page_sq), NEXT_PAGE_NOTE
    if tail != -1:
        return 0, tail + k, PREV_PAGE_NOTE
    return None


def render_page(pdf_path: Path, page: int, highlight_text: str | None, zoom: float = 1.5) -> tuple[bytes, str]:
    """(PNG bytes, note). Note is '' when fully highlighted or no highlight was requested."""
    doc = pymupdf.open(str(pdf_path))
    try:
        if not 1 <= page <= len(doc):
            return b"", f"không có trang {page} trong PDF"
        pg, note = doc[page - 1], ""
        if highlight_text:
            words = pg.get_text("words")
            found = _locate(words, squash(highlight_text))
            if found is None:
                note = NOT_FOUND_NOTE
            else:
                start, end, note = found
                pos = 0
                for w in words:
                    n = len(squash(w[4]))
                    if pos < end and pos + n > start and n:
                        pg.add_highlight_annot(pymupdf.Rect(w[:4]))
                    pos += n
        return pg.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), annots=True).tobytes("png"), note
    finally:
        doc.close()
