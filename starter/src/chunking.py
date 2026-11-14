"""Strategy A (fixed windows) and strategy B (one article per chunk) over a page-aware text stream."""
import hashlib
import re
from bisect import bisect_right
from typing import NamedTuple

from .config import A_OVERLAP, A_SIZE, B_MAX
from .models import Chunk, DocumentPage

_CHAPTER = re.compile(r"^Chương [IVXLC]+\s*$", re.MULTILINE)
_ARTICLE = re.compile(r"^Điều (\d+)\.\s*(.*)$", re.MULTILINE)


class PageSpan(NamedTuple):
    start: int
    end: int
    page: int
    printed_page: int | None


def build_stream(pages: list[DocumentPage]) -> tuple[str, list[PageSpan]]:
    """Join content pages with '\\n'; each span records which stream offsets came from which page."""
    parts, spans, pos = [], [], 0
    for p in pages:
        if not p.metadata.get("is_content", True):
            continue
        if parts:
            parts.append("\n")
            pos += 1
        parts.append(p.text)
        spans.append(PageSpan(pos, pos + len(p.text), p.page, p.metadata.get("printed_page")))
        pos += len(p.text)
    return "".join(parts), spans


def pages_for_span(spans: list[PageSpan], start: int, end: int) -> tuple[int, int, int | None]:
    """(page_start, page_end, printed_page_start) for stream range [start, end)."""
    starts = [s.start for s in spans]
    first = spans[max(0, bisect_right(starts, start) - 1)]
    last = spans[max(0, bisect_right(starts, max(start, end - 1)) - 1)]
    return first.page, last.page, first.printed_page


def structure_at(stream: str, offset: int) -> tuple[str | None, int | None, str | None]:
    """Nearest chapter and article headings at or before `offset`."""
    chuong = dieu = title = None
    for m in _CHAPTER.finditer(stream):
        if m.start() > offset:
            break
        chuong = m.group(0).strip()
    for m in _article_starts(stream):
        if m.start() > offset:
            break
        dieu, title = int(m.group(1)), m.group(2).strip()
    return chuong, dieu, title


def _make_chunk(chunk_id: str, strategy: str, page0: DocumentPage, text: str,
                spans: list[PageSpan], start: int, end: int,
                structure: tuple[str | None, int | None, str | None]) -> Chunk:
    page_start, page_end, printed = pages_for_span(spans, start, end)
    chuong, dieu, title = structure
    return Chunk(chunk_id=chunk_id, document_id=page0.document_id, source=page0.source,
                 page=page_start, text=text, metadata={
                     "strategy": strategy, "version": page0.metadata["version"],
                     "page_start": page_start, "page_end": page_end, "printed_page_start": printed,
                     "chuong": chuong, "dieu": dieu, "dieu_title": title, "char_count": len(text),
                     "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest()})


def fixed_size(pages: list[DocumentPage], size: int = A_SIZE, overlap: int = A_OVERLAP) -> list[Chunk]:
    """Overlapping character windows over one document's stream (never across documents)."""
    stream, spans = build_stream(pages)
    chunks, start, step = [], 0, size - overlap
    while start < len(stream):
        end = min(start + size, len(stream))
        chunks.append(_make_chunk(f"A:{pages[0].document_id}:{len(chunks):04d}", "A", pages[0],
                                  stream[start:end], spans, start, end, structure_at(stream, start)))
        if end == len(stream):
            break
        start += step
    return chunks


_HEADING_BREAK = re.compile(r"^(?:Chương [IVXLC]+|Mục \d+)\b", re.MULTILINE)
_CLAUSE = re.compile(r"^\d+\.\s", re.MULTILINE)
_SENTENCE_END = re.compile(r"(?<=[.;:])\s+")


def _article_starts(stream: str) -> list[re.Match]:
    """Article headings in increasing order; a 'Điều N.' line that breaks the sequence is a cross-reference."""
    found, last = [], 0
    for m in _ARTICLE.finditer(stream):
        n = int(m.group(1))
        if (last == 0 and not found) or last < n <= last + 3:
            found.append(m)
            last = n
    return found


def _pieces(stream: str, start: int, end: int, pattern: re.Pattern) -> list[tuple[int, int]]:
    """Split [start, end) of stream at pattern matches; returns (start, end) ranges."""
    cuts = [start] + [start + m.start() for m in pattern.finditer(stream[start:end]) if m.start() > 0] + [end]
    return [(a, b) for a, b in zip(cuts, cuts[1:]) if stream[a:b].strip()]


def _fit(stream: str, ranges: list[tuple[int, int]], limit: int) -> list[tuple[int, int]]:
    """Break any range longer than limit at sentence ends, then hard-cut if still too long."""
    out = []
    for a, b in ranges:
        if b - a <= limit:
            out.append((a, b))
            continue
        for s, e in _pieces(stream, a, b, _SENTENCE_END):
            while e - s > limit:
                out.append((s, s + limit))
                s += limit
            out.append((s, e))
    return out


def by_article(pages: list[DocumentPage], max_size: int = B_MAX) -> list[Chunk]:
    """One chunk per article; long articles are packed clause by clause, each part keeps the article header."""
    stream, spans = build_stream(pages)
    starts = _article_starts(stream)
    chunks = []
    for i, m in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else len(stream)
        brk = _HEADING_BREAK.search(stream, m.end(), end)
        end = brk.start() if brk else end
        header = m.group(0).strip()
        structure = structure_at(stream, m.start())
        body_start = m.end() + 1
        text = stream[m.start():end].strip()
        if len(text) <= max_size or body_start >= end:
            groups = [[(m.start(), end)]]
        else:
            limit = max_size - len(header) - 1
            ranges = _fit(stream, _pieces(stream, body_start, end, _CLAUSE), limit)
            groups, size = [[]], 0
            for a, b in ranges:
                piece = b - a + 1
                if groups[-1] and size + piece > limit:
                    groups.append([])
                    size = 0
                groups[-1].append((a, b))
                size += piece
        for part, group in enumerate(groups, start=1):
            a, b = group[0][0], group[-1][1]
            body = "\n".join(stream[x:y].strip() for x, y in group)
            part_text = body if len(groups) == 1 else f"{header}\n{body}"
            chunks.append(_make_chunk(f"B:{pages[0].document_id}:d{int(m.group(1)):03d}-p{part}", "B",
                                      pages[0], part_text, spans, a, b, structure))
    return chunks
