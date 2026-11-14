import csv
import json

import pytest

from src.evaluation import summarize
from src.explore import bench


class FakeEmbedder:
    def embed_query(self, q):
        return [0.0]


class FakeStore:
    def search(self, strategy, vec, top_k=3, filters=None):
        md = {"document_id": "blld-2019", "page_start": 1, "page_end": 1, "version": "2019", "dieu": 1}
        return [{"chunk_id": f"{strategy}:x", "text": "đoạn bằng chứng chính xác ở đây", "score": 0.9,
                 "parent_text": None, "metadata": md}]


def q(qid, split="dev"):
    return {"id": qid, "split": split, "question": "hỏi?", "gold_source_id": "blld-2019", "gold_page": 1,
            "evidence_quote": "đoạn bằng chứng chính xác ở đây", "filter": None}


@pytest.fixture
def frozen(monkeypatch):
    monkeypatch.setattr(bench, "assert_frozen", lambda *a, **k: None)


def test_rejects_test_split(frozen, tmp_path):
    with pytest.raises(ValueError):
        bench.run_explore_benchmark("D", [q("q1"), q("q2", "test")], FakeStore(), FakeEmbedder(), out_dir=tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_requires_frozen(monkeypatch, tmp_path):
    def refuse(*a, **k):
        raise SystemExit("benchmark not frozen")
    monkeypatch.setattr(bench, "assert_frozen", refuse)
    with pytest.raises(SystemExit):
        bench.run_explore_benchmark("D", [q("q1")], FakeStore(), FakeEmbedder(), out_dir=tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_writes_only_in_out_dir_and_metrics_match(frozen, tmp_path):
    traces = bench.run_explore_benchmark("D", [q("q1"), q("q2")], FakeStore(), FakeEmbedder(), out_dir=tmp_path)
    assert {p.name for p in tmp_path.iterdir()} == {"traces", "metrics.csv"}
    lines = (tmp_path / "traces" / "D_dev.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2 and json.loads(lines[0])["strategy"] == "D"
    row = next(csv.DictReader((tmp_path / "metrics.csv").open(encoding="utf-8")))
    s = summarize(traces)[0]
    assert (row["strategy"], int(row["n"]), int(row["hit1"]), int(row["hit3"])) == ("D", s["n"], s["hit1"], s["hit3"])


def test_metrics_keeps_other_strategies(frozen, tmp_path):
    bench.run_explore_benchmark("D", [q("q1")], FakeStore(), FakeEmbedder(), out_dir=tmp_path)
    bench.run_explore_benchmark("E", [q("q1")], FakeStore(), FakeEmbedder(), out_dir=tmp_path)
    rows = list(csv.DictReader((tmp_path / "metrics.csv").open(encoding="utf-8")))
    assert [r["strategy"] for r in rows] == ["D", "E"]
