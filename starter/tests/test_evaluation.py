from src.evaluation import evaluate_query, run_strategy, summarize

Q = {"id": "q01", "split": "dev", "question": "x", "gold_source_id": "blld-2019", "gold_page": 44, "gold_dieu": 105,
     "evidence_quote": "người sử dụng lao động phải thông báo bảng kê trả lương",
     "alt_gold": [{"source_id": "blld-2012", "page": 36, "dieu": 104,
                   "evidence_quote": "thời giờ làm việc bình thường không quá 08 giờ"}], "filter": None}


def hit(doc="blld-2019", ps=44, pe=44, text="... ng ười s ử dụng lao động phải thông báo bảng kê\ntrả lương ..."):
    return {"chunk_id": "c", "text": text, "score": 0.9,
            "metadata": {"document_id": doc, "page_start": ps, "page_end": pe, "version": doc[-4:]}}


def test_hit_requires_page_and_evidence():
    assert evaluate_query(Q, [hit(ps=50, pe=51)])["hit_at_3"] is False
    assert evaluate_query(Q, [hit(text="không liên quan")])["hit_at_3"] is False
    assert evaluate_query(Q, [hit()])["hit_at_1"] is True


def test_alt_gold_counts():
    r = evaluate_query(Q, [hit("blld-2012", 36, 37, "Thời giờ làm việc bình thường không quá 08 giờ trong 01 ngày")])
    assert r["hit_at_1"] is True


def test_hit_at_1_vs_3():
    r = evaluate_query(Q, [hit(text="khác"), hit(), hit(text="khác")])
    assert r["hit_positions"] == [False, True, False]
    assert r["hit_at_1"] is False and r["hit_at_3"] is True


def test_evidence_split_flagged():
    a = hit(text="... người sử dụng lao động phải thông báo")
    b = hit(text="bảng kê trả lương cho người lao động ...")
    r = evaluate_query(Q, [a, b])
    assert r["hit_at_3"] is False and "evidence_split" in r["errors"]


def test_summarize_counts():
    traces = [{"strategy": "A", "split": "dev", "hit_at_1": True, "hit_at_3": True},
              {"strategy": "A", "split": "dev", "hit_at_1": False, "hit_at_3": True},
              {"strategy": "A", "split": "dev", "hit_at_1": False, "hit_at_3": False}]
    assert summarize(traces) == [{"strategy": "A", "split": "dev", "n": 3, "hit1": 1, "hit3": 2}]


class FakeStore:
    def __init__(self):
        self.calls = []

    def search(self, strategy, qvec, top_k=3, filters=None):
        self.calls.append((strategy, filters))
        return [hit()]


class FakeEmbedder:
    def embed_query(self, q):
        return [0.0]


def test_filter_only_for_C():
    q_f = dict(Q, id="q02", filter={"version": "2019"})
    store = FakeStore()
    for s in ("A", "B", "C"):
        traces = run_strategy(s, [Q, q_f], store, FakeEmbedder())
        assert traces[1]["filter_applied"] == ({"version": "2019"} if s == "C" else None)
    assert store.calls == [("A", None), ("A", None), ("B", None), ("B", None), ("C", None), ("C", {"version": "2019"})]


def test_freeze_guard(tmp_path):
    import pytest

    from src.run import assert_frozen, freeze_benchmark
    qfile = tmp_path / "questions.jsonl"
    qfile.write_text('{"id": "q01"}\n', encoding="utf-8")
    with pytest.raises(SystemExit):
        assert_frozen(qfile)
    freeze_benchmark(qfile)
    assert_frozen(qfile)
    qfile.write_text('{"id": "q01", "split": "test"}\n', encoding="utf-8")
    with pytest.raises(SystemExit):
        assert_frozen(qfile)
