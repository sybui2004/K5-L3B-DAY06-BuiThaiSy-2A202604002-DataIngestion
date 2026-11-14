import os
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src.explore import services

APP = str(Path(__file__).resolve().parents[1] / "app.py")
QUESTION = "Ca làm đêm được tính từ mấy giờ?"
MD = {"document_id": "blld-2019", "version": "2019", "source": "data/raw/blld_2019_congbao.pdf", "page_start": 44,
      "page_end": 44, "printed_page_start": 46, "chuong": "Chương V", "dieu": 106, "dieu_title": "Giờ làm việc ban đêm",
      "char_count": 80, "content_hash": "h"}


class StubStore:
    def __init__(self, counts):
        self.counts, self.searches = counts, []

    def count(self, strategy=None):
        return self.counts[strategy]

    def search(self, strategy, vec, top_k=3, filters=None):
        self.searches.append((strategy, filters))
        return [{"chunk_id": f"{strategy}:blld-2019:{i:04d}", "text": f"đoạn {i}", "score": 0.9 - i / 10,
                 "parent_text": "văn bản cha" if strategy == "F" else None, "metadata": MD} for i in range(3)]

    def all_chunks(self, strategy):
        return []

    def sample_rows(self, strategy, limit=20):
        return []


class StubEmbedder:
    def __init__(self):
        self.calls = 0

    def embed_query(self, q):
        self.calls += 1
        return [0.0]


@dataclass
class Stub:
    store: StubStore
    embedder: StubEmbedder
    pages_by_doc: dict = field(default_factory=dict)
    health: dict = field(default_factory=lambda: {"postgres": None, "ollama": None})
    questions: list = field(default_factory=lambda: [
        {"id": "q02", "split": "dev", "question": QUESTION, "expected_answer": "22-06", "gold_source_id": "blld-2019",
         "gold_page": 44, "evidence_quote": "đoạn 0", "filter": None}])


COUNTS = {"A": 501, "B": 505, "C": 505, "D": 0, "E": 12, "F": 30}


@pytest.fixture
def stub(monkeypatch):
    s = Stub(StubStore(dict(COUNTS)), StubEmbedder())
    monkeypatch.setattr(services, "get_services", lambda: s)
    return s


def texts(at):
    return " ".join(str(e.value) for group in (at.markdown, at.caption, at.info, at.warning, at.error, at.code)
                    for e in group)


def test_app_loads_without_error(stub):
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert "Retrieval Lab" in texts(at) or at.title


def test_empty_question_shows_prompt_and_makes_no_embed_call(stub):
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.button(key="search").click().run()
    assert at.warning and stub.embedder.calls == 0


def test_unavailable_services_show_message(stub):
    stub.health = {"postgres": "Không kết nối được PostgreSQL. Chạy `docker compose up -d`", "ollama": None}
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert at.error and not at.exception
    assert "docker compose up -d" in texts(at)


def test_not_ingested_strategy_is_disabled_with_command(stub):
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.radio(key="strategy").set_value("D").run()
    assert "ingest --strategy D" in texts(at)
    assert at.button(key="search").disabled
    assert not at.exception


def test_search_calls_store_with_version_filter(stub):
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.radio(key="strategy").set_value("B")
    at.radio(key="year").set_value("2019")
    at.text_input(key="question").set_value(QUESTION).run()
    at.button(key="search").click().run()
    assert not at.exception
    assert stub.store.searches == [("B", {"version": "2019"})] and stub.embedder.calls == 1


def test_search_without_year_has_no_filter(stub):
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.text_input(key="question").set_value(QUESTION).run()
    at.button(key="search").click().run()
    assert stub.store.searches[0][1] is None


def test_compare_mode_searches_each_selected_strategy_once(stub):
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.multiselect(key="compare").set_value(["A", "F"])
    at.text_input(key="question").set_value(QUESTION).run()
    at.button(key="search").click().run()
    assert not at.exception
    assert sorted(s for s, _ in stub.store.searches) == ["A", "F"] and stub.embedder.calls == 1


def test_year_tab_searches_only_on_click(stub):
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.text_input(key="question").set_value(QUESTION).run()
    assert stub.store.searches == [] and stub.embedder.calls == 0
    at.button(key="year_compare").click().run()
    assert [f for _, f in stub.store.searches] == [None, {"version": "2019"}, {"version": "2012"}]


def test_each_result_shows_which_law_version(stub):
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.text_input(key="question").set_value(QUESTION).run()
    at.button(key="search").click().run()
    shown = [e.value for e in at.markdown if str(e.value).startswith("**#") and "Điều" in str(e.value)]
    assert len(shown) == 3 and all("Luật 2019" in s for s in shown)


def test_benchmark_tab_names_every_strategy(stub):
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert any("Fixed-size" in o and "Parent-child" not in o for o in at.multiselect(key="bench_strategies").options)
    legend = " ".join(str(e.value) for e in at.markdown)
    for name in ("Fixed-size", "Theo Điều", "Recursive", "Semantic", "Parent-child"):
        assert name in legend
    assert "bài nộp" in legend and "khám phá" in legend


def test_audit_tab_shows_coherence_summary_and_provenance(stub, monkeypatch, tmp_path):
    from src import config
    from tests.test_explore_audit_view import row, write
    audit = tmp_path / "audit"
    audit.mkdir()
    write(audit / "coherence.csv", [row("p1", "A", "0"), row("p1", "B", "2")])
    monkeypatch.setattr(config, "RESULTS_DIR", tmp_path)
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert "Audit" in [t.label for t in at.tabs]
    assert any(df.value["mean"].tolist() == [0.0, 2.0] for df in at.dataframe if "mean" in df.value)
    assert any("metadata.csv" in str(e.value) for e in at.info)  # metadata/grounding files absent


def test_audit_tab_without_files_does_not_crash(stub, monkeypatch, tmp_path):
    from src import config
    monkeypatch.setattr(config, "RESULTS_DIR", tmp_path)
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception and "Audit" in [t.label for t in at.tabs]
