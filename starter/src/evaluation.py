"""Automatic retrieval scoring (Hit@1, Evidence Hit@3) and per-query traces.

Human labels (coherence, grounding) are never inferred here.
"""
import re
import unicodedata

_WS = re.compile(r"\s+")


def squash(text: str) -> str:
    """NFC + lowercase + remove all whitespace, so PDF line breaks / split syllables cannot hide a match."""
    return _WS.sub("", unicodedata.normalize("NFC", text).lower())


def gold_entries(q: dict) -> list[dict]:
    """Primary gold plus every documented alternative, in one shape."""
    primary = {"source_id": q["gold_source_id"], "page": q["gold_page"], "dieu": q.get("gold_dieu"),
               "evidence_quote": q["evidence_quote"]}
    return [primary] + list(q.get("alt_gold") or [])


def _pages(g: dict) -> set[int]:
    return set(g["page"]) if isinstance(g["page"], list) else {g["page"]}


def _on_gold_page(h: dict, g: dict) -> bool:
    md = h["metadata"]
    return md["document_id"] == g["source_id"] and any(md["page_start"] <= p <= md["page_end"] for p in _pages(g))


def is_hit(h: dict, q: dict) -> bool:
    """Same source, overlapping gold page, and the whole evidence quote inside the chunk."""
    text = squash(h["text"])
    return any(_on_gold_page(h, g) and squash(g["evidence_quote"]) in text for g in gold_entries(q))


def _evidence_split(q: dict, hits: list[dict]) -> bool:
    for g in gold_entries(q):
        quote = squash(g["evidence_quote"])
        k = max(10, int(len(quote) * 0.3))
        on_page = [squash(h["text"]) for h in hits if _on_gold_page(h, g)]
        heads = {i for i, t in enumerate(on_page) if quote[:k] in t}
        tails = {i for i, t in enumerate(on_page) if quote[-k:] in t}
        if heads and tails and heads != tails:
            return True
    return False


def evaluate_query(question: dict, hits: list[dict]) -> dict:
    positions = [is_hit(h, question) for h in hits]
    errors = []
    if not any(positions) and _evidence_split(question, hits):
        errors.append("evidence_split")
    return {"question_id": question["id"], "split": question["split"], "hit_positions": positions,
            "hit_at_1": bool(positions[:1]) and positions[0], "hit_at_3": any(positions[:3]), "errors": errors}


def run_strategy(strategy: str, questions: list[dict], store, embedder, top_k: int = 3) -> list[dict]:
    """Retrieve top-k for every question; only strategy C applies the question's metadata filter."""
    traces = []
    for q in questions:
        flt = q.get("filter") if strategy == "C" else None
        hits = store.search(strategy, embedder.embed_query(q["question"]), top_k=top_k, filters=flt)
        result = evaluate_query(q, hits)
        traces.append({"strategy": strategy, **result, "question": q["question"], "filter_in_question": q.get("filter"),
                       "filter_applied": flt, "top_k": [
                           {"rank": i + 1, "chunk_id": h["chunk_id"], "score": round(h["score"], 4),
                            "metadata": h["metadata"], "text": h["text"], "hit": result["hit_positions"][i]}
                           for i, h in enumerate(hits)]})
    return traces


def summarize(traces: list[dict]) -> list[dict]:
    rows: dict[tuple, dict] = {}
    for t in traces:
        r = rows.setdefault((t["strategy"], t["split"]), {"strategy": t["strategy"], "split": t["split"],
                                                          "n": 0, "hit1": 0, "hit3": 0})
        r["n"] += 1
        r["hit1"] += int(t["hit_at_1"])
        r["hit3"] += int(t["hit_at_3"])
    return list(rows.values())
