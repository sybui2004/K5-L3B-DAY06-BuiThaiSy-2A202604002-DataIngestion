import hashlib

import pytest

from src import config
from src.models import Chunk
from src.store import PgVectorStore

pytestmark = pytest.mark.db
DIM = 1024


def vec(i: int) -> list[float]:
    v = [0.0] * DIM
    v[i % DIM] = 1.0
    return v


def chunk(strategy: str, i: int, version: str = "2019", doc: str = "blld-2019") -> Chunk:
    text = f"nội dung {i}"
    return Chunk(chunk_id=f"{strategy}:{doc}:{i:04d}", document_id=doc, source=f"{doc}.pdf", page=1, text=text,
                 metadata={"strategy": strategy, "version": version, "page_start": 1, "page_end": 2,
                           "printed_page_start": 3, "chuong": "Chương I", "dieu": i, "dieu_title": "t",
                           "char_count": len(text), "content_hash": hashlib.sha256(text.encode()).hexdigest()})


@pytest.fixture
def store():
    s = PgVectorStore(config.DATABASE_URL, DIM, table="chunks_test")
    s.drop()
    s.create_schema()
    yield s
    s.drop()


def test_upsert_idempotent(store):
    cs = [chunk("A", i) for i in range(5)]
    store.upsert("A", cs, [vec(i) for i in range(5)])
    store.upsert("A", cs, [vec(i) for i in range(5)])
    assert store.count("A") == 5


def test_obsolete_chunks_deleted(store):
    store.upsert("A", [chunk("A", i) for i in range(5)], [vec(i) for i in range(5)])
    result = store.upsert("A", [chunk("A", i) for i in range(3)], [vec(i) for i in range(3)])
    assert store.count("A") == 3 and result["deleted"] == 2


def test_dimension_mismatch_raises(store):
    with pytest.raises(ValueError):
        store.upsert("A", [chunk("A", 0)], [[0.1, 0.2, 0.3]])
    with pytest.raises(ValueError):
        store.upsert("A", [chunk("A", 0), chunk("A", 1)], [vec(0)])


def test_filter_restricts_version(store):
    cs = [chunk("B", 0, "2012", "blld-2012"), chunk("B", 1, "2012", "blld-2012"), chunk("B", 2), chunk("B", 3)]
    store.upsert("B", cs, [vec(i) for i in range(4)])
    hits = store.search("B", vec(0), top_k=3, filters={"version": "2019"})
    assert hits and all(h["metadata"]["version"] == "2019" for h in hits)
    with pytest.raises(ValueError):
        store.search("B", vec(0), filters={"chuong": "x"})


def test_copy_strategy(store):
    store.upsert("B", [chunk("B", i) for i in range(4)], [vec(i) for i in range(4)])
    assert store.copy_strategy("B", "C") == 4
    store.copy_strategy("B", "C")
    assert store.count("C") == store.count("B") == 4
    hits = store.search("C", vec(1))
    assert all(h["chunk_id"].startswith("C:") for h in hits)


def test_search_order_and_score(store):
    store.upsert("A", [chunk("A", i) for i in range(5)], [vec(i) for i in range(5)])
    hits = store.search("A", vec(2), top_k=3)
    assert len(hits) == 3 and hits[0]["chunk_id"] == "A:blld-2019:0002"
    assert hits[0]["score"] == pytest.approx(1.0)
    md = hits[0]["metadata"]
    assert md["document_id"] == "blld-2019" and md["page_start"] == 1 and md["page_end"] == 2 and md["dieu"] == 2


def test_existing_hashes(store):
    store.upsert("A", [chunk("A", 0)], [vec(0)])
    assert store.existing_hashes("A", "blld-2019") == {"A:blld-2019:0000": chunk("A", 0).metadata["content_hash"]}


def test_delete_obsolete_without_reembedding(store):
    store.upsert("A", [chunk("A", i) for i in range(4)], [vec(i) for i in range(4)])
    assert store.delete_obsolete("A", "blld-2019", {"A:blld-2019:0000", "A:blld-2019:0001"}) == 2
    assert store.count("A") == 2


def _tables(store, prefix):
    with store._connect() as conn:
        rows = conn.execute("SELECT table_name FROM information_schema.tables WHERE table_name LIKE %s",
                            (prefix + r"\_%",)).fetchall()
    return {r[0] for r in rows}


def _columns(store, table):
    with store._connect() as conn:
        rows = conn.execute("SELECT column_name FROM information_schema.columns WHERE table_name=%s",
                            (table,)).fetchall()
    return {r[0] for r in rows}


def test_each_strategy_has_own_table(store):
    assert _tables(store, "chunks_test") == {f"chunks_test_{c}" for c in "abcdef"}
    assert "parent_text" in _columns(store, "chunks_test_f")
    assert "parent_text" not in _columns(store, "chunks_test_b")


def test_upsert_goes_to_strategy_table(store):
    store.upsert("B", [chunk("B", i) for i in range(3)], [vec(i) for i in range(3)])
    assert store.count("B") == 3 and store.count("A") == 0 and store.count() == 3


def test_unknown_strategy_rejected(store):
    with pytest.raises(ValueError):
        store.upsert("Z", [chunk("Z", 0)], [vec(0)])
    with pytest.raises(ValueError):
        store.count("Z")


def test_search_isolated_per_strategy(store):
    store.upsert("A", [chunk("A", 0)], [vec(0)])
    store.upsert("B", [chunk("B", 0)], [vec(0)])
    hits = store.search("A", vec(0), top_k=3)
    assert [h["chunk_id"] for h in hits] == ["A:blld-2019:0000"]


def test_copy_strategy_b_to_c(store):
    store.upsert("B", [chunk("B", i) for i in range(3)], [vec(i) for i in range(3)])
    assert store.copy_strategy("B", "C") == 3
    assert store.count("C") == 3
    assert {h["chunk_id"] for h in store.search("C", vec(0), top_k=3)} == {f"C:blld-2019:{i:04d}" for i in range(3)}


def test_drop_removes_only_prefixed_tables(store):
    with store._connect() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS chunks_test_keepme (x int)")
    try:
        store.drop()
        assert _tables(store, "chunks_test") == {"chunks_test_keepme"}
    finally:
        with store._connect() as conn:
            conn.execute("DROP TABLE IF EXISTS chunks_test_keepme")


def test_f_upsert_and_search_returns_parent_text(store):
    c = chunk("F", 0)
    c.metadata.update(parent_id="B:blld-2019:d000-p1", parent_text="văn bản cha")
    store.upsert("F", [c], [vec(0)])
    hit = store.search("F", vec(0), top_k=1)[0]
    assert hit["parent_text"] == "văn bản cha"


def test_non_f_search_has_parent_text_none(store):
    store.upsert("A", [chunk("A", 0)], [vec(0)])
    assert store.search("A", vec(0), top_k=1)[0]["parent_text"] is None


def test_upsert_prune_false_keeps_unchanged_rows(store):
    store.upsert("A", [chunk("A", i) for i in range(5)], [vec(i) for i in range(5)])
    result = store.upsert("A", [chunk("A", 0)], [vec(0)], prune=False)
    assert store.count("A") == 5 and result["deleted"] == 0


def test_sample_rows_excludes_embedding_and_is_limited(store):
    store.upsert("B", [chunk("B", i) for i in range(5)], [vec(i) for i in range(5)])
    rows = store.sample_rows("B", limit=3)
    assert len(rows) == 3 and "embedding" not in rows[0]
    assert {"chunk_id", "version", "page_start", "page_end", "dieu", "text"} <= set(rows[0])
