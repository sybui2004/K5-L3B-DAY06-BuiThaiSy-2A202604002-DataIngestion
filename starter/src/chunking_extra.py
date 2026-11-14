"""Exploration strategies D (recursive), E (semantic) and F (parent-child) over the page-aware text stream."""
import hashlib
import math
import re
from typing import Callable

from .chunking import _CLAUSE, _fit, _make_chunk, _pieces, build_stream, by_article, structure_at
from .config import D_OVERLAP, D_SIZE, E_MAX, E_MIN, E_SIM_THRESHOLD, F_CHILD_SIZE
from .models import Chunk, DocumentPage

_SEPARATORS = ("\n\n", "\n", ". ", " ")


def _cut_point(stream: str, hard_end: int, min_end: int) -> int:
    """Position just after the highest-priority separator found in [min_end, hard_end); hard cut otherwise."""
    for sep in _SEPARATORS:
        i = stream.rfind(sep, min_end, hard_end)
        if i != -1:
            return i + len(sep)
    return hard_end


def recursive(pages: list[DocumentPage], size: int = D_SIZE, overlap: int = D_OVERLAP) -> list[Chunk]:
    """Windows of at most `size` chars that end at paragraph > line > sentence > word boundaries."""
    stream, spans = build_stream(pages)
    chunks, start, n = [], 0, len(stream)
    while start < n:
        hard = min(start + size, n)
        end = n if hard == n else _cut_point(stream, hard, start + size // 2)
        text = stream[start:end].strip()
        if text:
            chunks.append(_make_chunk(f"D:{pages[0].document_id}:{len(chunks):04d}", "D", pages[0], text,
                                      spans, start, end, structure_at(stream, start)))
        if end >= n:
            break
        nxt = max(end - overlap, start + 1)
        while nxt < end and not stream[nxt - 1].isspace():  # never start in the middle of a word
            nxt += 1
        start = nxt
    return chunks


_BOUNDARY = re.compile(r"(?P<punct>[.;:])\s+|[\n]+")
_HEADING_STUB = re.compile(r"^\s*Điều \d+$")


def split_sentences(text: str) -> list[tuple[int, int]]:
    """(start, end) offsets of sentences: cut after . ; : and at line breaks, but not after 'Điều N'."""
    out, pos = [], 0
    for m in _BOUNDARY.finditer(text):
        if m.group("punct") == "." and _HEADING_STUB.match(text[pos:m.start()]):
            continue
        end = m.start() + (1 if m.group("punct") else 0)
        if text[pos:end].strip():
            out.append((pos, end))
        pos = m.end()
    if text[pos:].strip():
        out.append((pos, len(text)))
    return out


def _cosine(a: list[float], b: list[float]) -> float:
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b)) / (na * nb) if na and nb else 0.0


def semantic(pages: list[DocumentPage], embed: Callable[[list[str]], list[list[float]]],
             threshold: float = E_SIM_THRESHOLD, max_size: int = E_MAX, min_size: int = E_MIN) -> list[Chunk]:
    """Embed every sentence once; cut where adjacent sentences are less similar than `threshold` or size exceeds."""
    stream, spans = build_stream(pages)
    sents = []
    for a, b in split_sentences(stream):
        while b - a > max_size:  # a single oversized sentence is hard-cut
            sents.append((a, a + max_size))
            a += max_size
        sents.append((a, b))
    if not sents:
        return []
    vecs = embed([stream[a:b] for a, b in sents])
    chunks, g_start, g_end = [], sents[0][0], sents[0][1]

    def emit(start: int, end: int) -> None:
        text = stream[start:end].strip()
        if text:
            chunks.append(_make_chunk(f"E:{pages[0].document_id}:{len(chunks):04d}", "E", pages[0], text,
                                      spans, start, end, structure_at(stream, start)))

    for i in range(1, len(sents)):
        a, b = sents[i]
        similar = _cosine(vecs[i - 1], vecs[i]) >= threshold or g_end - g_start < min_size
        if similar and b - g_start <= max_size:
            g_end = b
        else:
            emit(g_start, g_end)
            g_start, g_end = a, b
    emit(g_start, g_end)
    return chunks


def _child_ranges(text: str, child_size: int) -> list[tuple[int, int]]:
    """Contiguous ranges of `text`, each at most `child_size`, cut at clause/sentence boundaries."""
    pieces = _fit(text, _pieces(text, 0, len(text), _CLAUSE), child_size)
    ranges, start, end = [], None, None
    for a, b in pieces:
        if start is not None and b - start > child_size:
            ranges.append((start, end))
            start = None
        if start is None:
            start = a
        end = b
    if start is not None:
        ranges.append((start, end))
    return ranges


def parent_child(pages: list[DocumentPage], child_size: int = F_CHILD_SIZE) -> list[Chunk]:
    """Small child chunks (searched) that remember their parent article chunk (returned for context)."""
    children = []
    for parent in by_article(pages):
        suffix = parent.chunk_id.split(":", 2)[2]  # d001-p1
        n = 0
        for a, b in _child_ranges(parent.text, child_size):
            text = parent.text[a:b].strip()
            if not text:
                continue
            md = {**parent.metadata, "strategy": "F", "char_count": len(text),
                  "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                  "parent_id": parent.chunk_id, "parent_text": parent.text}
            children.append(Chunk(chunk_id=f"F:{parent.document_id}:{suffix}-c{n:02d}", document_id=parent.document_id,
                                  source=parent.source, page=parent.page, text=text, metadata=md))
            n += 1
    return children
