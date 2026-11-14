import csv

from src.audit import coherence_rows, grounding_rows, metadata_rows, summarize_audit, write_rows
from tests.conftest import make_page


class FakeStore:
    def all_chunks(self, strategy):
        return [{"chunk_id": f"{strategy}:blld-2019:{p:04d}", "text": f"đầu trang {p} nội dung luật lao động " * 3,
                 "metadata": {"document_id": "blld-2019", "page_start": p, "page_end": p}} for p in range(1, 60)]


def pages():
    return {"blld-2019": [make_page(p, f"đầu trang {p} nội dung luật lao động " * 10) for p in range(1, 60)]}


def trace(strategy, qid, flt=None):
    return {"strategy": strategy, "question_id": qid, "question": "q", "filter_in_question": flt, "filter_applied": flt,
            "top_k": [{"rank": r, "chunk_id": f"{strategy}:c{r}", "text": "t", "score": 0.5,
                       "metadata": {"document_id": "blld-2019", "source": "s", "page_start": 1, "page_end": 1,
                                    "version": "2019", "dieu": 1}} for r in (1, 2, 3)]}


def test_coherence_positions_fixed():
    rows = coherence_rows(FakeStore(), pages())
    assert len(rows) == 5 * 3
    assert {r["pdf_page"] for r in rows} == {5, 15, 25, 35, 45}
    assert all(r["chunk_id"] for r in rows)
    assert all(r["score_0_2"] == "" for r in rows)
    assert all(r["reason"].startswith("trùng") for r in rows if r["strategy"] == "C")


def test_templates_have_empty_label_columns():
    traces = [trace(s, f"q{i}") for s in "ABC" for i in range(16, 21)]
    md = metadata_rows(traces)
    assert len(md) == 5 * 3 * 3
    assert all(r[k] == "" for r in md for k in ("source_ok", "page_ok", "version_ok", "dieu_ok", "filter_ok", "note"))
    gr = grounding_rows(traces, {f"q{i}": "đáp án" for i in range(16, 21)})
    assert len(gr) == 15 and all(r["score_0_2"] == "" and r["reason"] == "" for r in gr)


def test_audit_summary_counts(tmp_path):
    traces = [trace("A", "q16", {"version": "2019"}), trace("A", "q17")]
    md = metadata_rows(traces)
    for i, r in enumerate(md):
        r.update(source_ok="1", page_ok="1", version_ok="1", dieu_ok="0" if i == 0 else "1",
                 filter_ok="1" if r["filter"] else "")
    gr = grounding_rows(traces, {"q16": "x", "q17": "y"})
    gr[0]["score_0_2"], gr[1]["score_0_2"] = "2", "1"
    co = [{"strategy": "A", "score_0_2": "2"}, {"strategy": "A", "score_0_2": "1"}]
    for name, rows in (("coherence", co), ("metadata", md), ("grounding", gr)):
        write_rows(tmp_path / f"{name}.csv", rows)
    s = {r["strategy"]: r for r in summarize_audit(tmp_path)}["A"]
    assert s["coherence_mean"] == 1.5 and s["coherence_n"] == 2
    assert s["metadata_ok"] == "5/6"
    assert s["filter_ok"] == "1/1"
    assert s["grounding_counts"] == "0:0 1:1 2:1" and s["grounding_mean"] == 1.5
