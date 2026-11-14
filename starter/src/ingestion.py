"""Read Công báo PDFs and normalize their text, keeping page traceability."""
import re
import unicodedata
from collections import Counter
from pathlib import Path

import pymupdf

from .config import MIN_PAGE_CHARS
from .models import DocumentPage

# "  CÔNG BÁO/Số 993 + 994/Ngày 26-12-2019 43" or "4 CÔNG BÁO/Số 993 + 994/Ngày 26-12-2019"
_HEADER = re.compile(r"^\s*(\d+)?\s*CÔNG BÁO/Số[^\n]*?Ngày\s+\S+\s*(\d+)?\s*$", re.MULTILINE)
_GLYPH_DIGIT_DASH = re.compile(r"(?<=\d)ộ(?=\d)")
_GLYPH_SPACED_DASH = re.compile(r"(?<= )Ị(?= )")
_SPACES = re.compile(r"[ \t ]+")
# A Vietnamese syllable never consists of consonants only: such a token is a split syllable.
_CONSONANT_ONLY = re.compile(r"(?<!\w)(?:ngh|ng|nh|th|tr|ch|ph|kh|gh|[bcdđghklmnpqrstvx])(?= \w)")


def normalize_text(text: str, stats: Counter | None = None) -> str:
    """NFC, repair dash glyphs only in unambiguous contexts, collapse spaces, keep line breaks."""
    text = unicodedata.normalize("NFC", text)
    text, n1 = _GLYPH_DIGIT_DASH.subn("-", text)
    text, n2 = _GLYPH_SPACED_DASH.subn("-", text)
    if stats is not None:
        stats["glyph_dash_fixed"] += n1 + n2
    lines = (_SPACES.sub(" ", line).strip() for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def strip_gazette_header(text: str) -> tuple[str, int | None]:
    """Remove the per-page 'CÔNG BÁO/Số …' line; return remaining text and the printed page number."""
    text = unicodedata.normalize("NFC", text)
    match = _HEADER.search(text)
    if not match:
        return text.strip(), None
    printed = match.group(1) or match.group(2)
    rest = (text[: match.start()] + text[match.end():]).strip()
    return rest, int(printed) if printed else None


def count_split_syllables(text: str) -> int:
    """Rough count of syllables broken by spurious spaces (measurement only, text is not changed)."""
    return len(_CONSONANT_ONLY.findall(text.lower()))


def load_pdf(path: Path, document_id: str, source: str, version: str,
             stats: Counter | None = None) -> list[DocumentPage]:
    """Extract every physical page (1-based) with its printed page and content flag."""
    pages = []
    for i, page in enumerate(pymupdf.open(str(path)), start=1):
        raw, printed = strip_gazette_header(page.get_text())
        text = normalize_text(raw, stats)
        pages.append(DocumentPage(
            document_id=document_id, source=source, page=i, text=text,
            metadata={
                "version": version,
                "printed_page": printed,
                "is_content": len(text) >= MIN_PAGE_CHARS,
                "char_count": len(text),
                "split_syllable_suspects": count_split_syllables(text),
            },
        ))
    return pages
