import json

import pytest

from src import run
from src.ingest_extra import ingest_extra


class FakeStore:
    def __init__(self):
        self.rows: dict[tuple[str, str], str] = {}
        self.strategies_used: set[str] = set()
        self.prune_args: list[bool] = []

    def existing_hashes(self, strategy, document_id):
        self.strategies_used.add(strategy)
        return {cid: h for (s, cid), h in self.rows.items() if s == strategy and f":{document_id}:" in cid}

    def upsert(self, strategy, chunks, vectors, prune=True):
        self.strategies_used.add(strategy)
        self.prune_args.append(prune)
        assert len(chunks) == len(vectors)
        for c in chunks:
            self.rows[(strategy, c.chunk_id)] = c.metadata["content_hash"]
        return {"upserted": len(chunks), "deleted": 0}

    def delete_obsolete(self, strategy, document_id, keep):
        self.strategies_used.add(strategy)
        gone = [k for k in self.rows if k[0] == strategy and f":{document_id}:" in k[1] and k[1] not in keep]
        for k in gone:
            del self.rows[k]
        return len(gone)


class FakeEmbedder:
    model_name, dimensions = "fake", 3

    def embed_documents(self, texts):
        return [[1.0, 0.0, float(len(t) % 7)] for t in texts]


@pytest.fixture
def corpus(synthetic_pages):
    return {"blld-2019": synthetic_pages}


@pytest.mark.parametrize("strategy", ["D", "E", "F"])
def test_ingest_embeds_only_new_or_changed(strategy, corpus, tmp_path):
    store, emb = FakeStore(), FakeEmbedder()
    first = ingest_extra(strategy, store, emb, corpus, results_dir=tmp_path)
    second = ingest_extra(strategy, store, emb, corpus, results_dir=tmp_path)
    assert first["embedded_count"] == first["chunk_count"] > 0
    assert second["embedded_count"] == 0 and second["chunk_count"] == first["chunk_count"]


def test_ingest_rejects_official_strategies(corpus, tmp_path):
    for s in "ABC":
        with pytest.raises(ValueError):
            ingest_extra(s, FakeStore(), FakeEmbedder(), corpus, results_dir=tmp_path)


def test_ingest_never_touches_other_strategies(corpus, tmp_path):
    store = FakeStore()
    ingest_extra("D", store, FakeEmbedder(), corpus, results_dir=tmp_path)
    assert store.strategies_used == {"D"}


def test_ingest_never_prunes_during_upsert(corpus, tmp_path):
    store = FakeStore()
    ingest_extra("D", store, FakeEmbedder(), corpus, results_dir=tmp_path)
    assert store.prune_args and not any(store.prune_args)


def test_ingest_writes_only_under_results_dir(corpus, tmp_path):
    out = ingest_extra("F", FakeStore(), FakeEmbedder(), corpus, results_dir=tmp_path)
    written = json.loads((tmp_path / "ingest_F.json").read_text(encoding="utf-8"))
    assert written["strategy"] == "F" and written["chunk_count"] == out["chunk_count"]
    assert {p.name for p in tmp_path.iterdir()} == {"ingest_F.json"}
    assert set(out) >= {"len_min", "len_mean", "len_p50", "len_p95", "len_max", "ingest_seconds"}


def test_cli_default_ingest_unchanged(monkeypatch):
    calls = []
    monkeypatch.setattr(run, "ingest", lambda max_pages=None: calls.append(("ingest", max_pages)) or {})
    monkeypatch.setattr(run, "ingest_extra_cmd", lambda s: calls.append(("extra", s)) or {})
    run.main(["ingest"])
    run.main(["ingest", "--strategy", "D"])
    assert calls == [("ingest", None), ("extra", "D")]
