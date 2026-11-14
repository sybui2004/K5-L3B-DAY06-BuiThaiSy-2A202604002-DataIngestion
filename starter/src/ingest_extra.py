"""Ingest exploration strategies D/E/F into their own tables (never touches A/B/C or the submission results)."""
import json
import statistics
import time
from pathlib import Path

from .chunking_extra import parent_child, recursive, semantic
from .config import EXPLORE_DIR


def length_stats(lengths: list[int]) -> dict:
    s = sorted(lengths)
    return {"len_min": s[0], "len_mean": round(statistics.mean(s), 1), "len_p50": s[len(s) // 2],
            "len_p95": s[int(len(s) * 0.95) - 1], "len_max": s[-1], "total_chars": sum(s)}


def _chunker(strategy: str, embedder):
    if strategy == "D":
        return recursive
    if strategy == "E":
        return lambda pages: semantic(pages, embedder.embed_documents)
    if strategy == "F":
        return parent_child
    raise ValueError(f"ingest_extra handles D/E/F only, got {strategy!r}")


def ingest_extra(strategy: str, store, embedder, pages_by_doc: dict, results_dir: Path = EXPLORE_DIR) -> dict:
    chunker = _chunker(strategy, embedder)
    t0, embedded, all_chunks = time.perf_counter(), 0, []
    for doc_id, pages in pages_by_doc.items():
        chunks = chunker(pages)
        known = store.existing_hashes(strategy, doc_id)
        todo = [c for c in chunks if known.get(c.chunk_id) != c.metadata["content_hash"]]
        if todo:
            store.upsert(strategy, todo, embedder.embed_documents([c.text for c in todo]), prune=False)
        store.delete_obsolete(strategy, doc_id, {c.chunk_id for c in chunks})
        embedded += len(todo)
        all_chunks += chunks
    out = {"strategy": strategy, "chunk_count": len(all_chunks), "embedded_count": embedded,
           "ingest_seconds": round(time.perf_counter() - t0, 1),
           **length_stats([len(c.text) for c in all_chunks])}
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / f"ingest_{strategy}.json").write_text(json.dumps(out, ensure_ascii=False, indent=2),
                                                         encoding="utf-8")
    return out
