"""Manual-audit templates (label columns left empty for the author) and their summary.

Nothing here assigns a coherence, metadata or grounding label: the author grades the CSVs by hand.
"""
import csv
from collections import defaultdict
from pathlib import Path

from .config import COHERENCE_PAGES
from .evaluation import squash

PROBE_CHARS = 40
COHERENCE_FIELDS = ["position_id", "document_id", "pdf_page", "position_text", "strategy", "chunk_id",
                    "chunk_text", "score_0_2", "reason"]
METADATA_FIELDS = ["question_id", "strategy", "rank", "chunk_id", "source", "page_start", "page_end", "version",
                   "dieu", "filter", "source_ok", "page_ok", "version_ok", "dieu_ok", "filter_ok", "note"]
GROUNDING_FIELDS = ["question_id", "strategy", "question", "expected_answer", "top3_chunk_ids", "top3_text",
                    "score_0_2", "reason"]


def coherence_rows(store, pages_by_doc: dict, strategies=("A", "B", "C")) -> list[dict]:
    """Fixed positions = start of content on PDF pages COHERENCE_PAGES of each document (chosen before scoring).

    The chunk 'containing' a position is the first chunk (by chunk_id) on that page whose text contains the
    page's first PROBE_CHARS characters.
    """
    rows = []
    chunks = {s: store.all_chunks(s) for s in strategies}
    for doc, pages in pages_by_doc.items():
        by_page = {p.page: p for p in pages}
        for page in COHERENCE_PAGES:
            probe = squash(by_page[page].text[:PROBE_CHARS])
            pid = f"{doc}@p{page}"
            for s in strategies:
                match = next((c for c in chunks[s] if c["metadata"]["document_id"] == doc
                              and c["metadata"]["page_start"] <= page <= c["metadata"]["page_end"]
                              and probe in squash(c["text"])), None)
                rows.append({"position_id": pid, "document_id": doc, "pdf_page": page,
                             "position_text": by_page[page].text[:PROBE_CHARS], "strategy": s,
                             "chunk_id": match["chunk_id"] if match else "",
                             "chunk_text": match["text"] if match else "", "score_0_2": "",
                             "reason": "trùng chunk B — C dùng chung chunk với B, chấm giống dòng B" if s == "C" else ""})
    return rows


def metadata_rows(test_traces: list[dict]) -> list[dict]:
    rows = []
    for t in test_traces:
        for h in t["top_k"]:
            md = h["metadata"]
            rows.append({"question_id": t["question_id"], "strategy": t["strategy"], "rank": h["rank"],
                         "chunk_id": h["chunk_id"], "source": md.get("source"), "page_start": md["page_start"],
                         "page_end": md["page_end"], "version": md["version"], "dieu": md.get("dieu"),
                         # requested filter (from the question), so A/B rows are also checked for compliance
                         "filter": (t["filter_in_question"] or {}).get("version", ""),
                         "source_ok": "", "page_ok": "", "version_ok": "", "dieu_ok": "", "filter_ok": "", "note": ""})
    return rows


def grounding_rows(test_traces: list[dict], expected: dict[str, str]) -> list[dict]:
    return [{"question_id": t["question_id"], "strategy": t["strategy"], "question": t["question"],
             "expected_answer": expected[t["question_id"]],
             "top3_chunk_ids": " | ".join(h["chunk_id"] for h in t["top_k"]),
             "top3_text": "\n---\n".join(h["text"] for h in t["top_k"]), "score_0_2": "", "reason": ""}
            for t in test_traces]


def write_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def _read(path: Path) -> list[dict]:
    return list(csv.DictReader(path.open(encoding="utf-8-sig")))


def summarize_audit(audit_dir: Path) -> list[dict]:
    out = defaultdict(dict)
    co = defaultdict(list)
    for r in _read(audit_dir / "coherence.csv"):
        if r["score_0_2"] != "":
            co[r["strategy"]].append(int(r["score_0_2"]))
    for s, v in co.items():
        out[s].update(coherence_n=len(v), coherence_mean=round(sum(v) / len(v), 2))
    md, flt = defaultdict(lambda: [0, 0]), defaultdict(lambda: defaultdict(list))
    for r in _read(audit_dir / "metadata.csv"):
        md[r["strategy"]][1] += 1
        md[r["strategy"]][0] += all(r[k] == "1" for k in ("source_ok", "page_ok", "version_ok", "dieu_ok"))
        if r["filter"]:
            flt[r["strategy"]][r["question_id"]].append(r["filter_ok"] == "1")
    for s, (ok, n) in md.items():
        qs = flt[s]
        out[s].update(metadata_ok=f"{ok}/{n}",
                      filter_ok=f"{sum(all(v) for v in qs.values())}/{len(qs)}" if qs else "N/A")
    gr = defaultdict(list)
    for r in _read(audit_dir / "grounding.csv"):
        if r["score_0_2"] != "":
            gr[r["strategy"]].append(int(r["score_0_2"]))
    for s, v in gr.items():
        out[s].update(grounding_counts=" ".join(f"{k}:{v.count(k)}" for k in (0, 1, 2)),
                      grounding_mean=round(sum(v) / len(v), 2), grounding_n=len(v))
    return [{"strategy": s, **vals} for s, vals in sorted(out.items())]
