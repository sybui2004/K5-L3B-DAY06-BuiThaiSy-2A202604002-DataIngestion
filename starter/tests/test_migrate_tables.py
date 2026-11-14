import pytest

from src import config
from src.store import PgVectorStore, _vec
from tests.test_store import chunk, vec

pytestmark = pytest.mark.db
DIM = 1024
LEGACY = "legacy_test"
COUNTS = {"A": 3, "B": 2, "C": 2}


@pytest.fixture
def store():
    s = PgVectorStore(config.DATABASE_URL, DIM, table="chunks_mig")
    s.drop()
    with s._connect() as conn:
        conn.execute(f"DROP TABLE IF EXISTS {LEGACY}")
    # legacy single-table layout: one table with a strategy column
    with s._connect() as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.execute(f"""CREATE TABLE {LEGACY} (
            chunk_id TEXT PRIMARY KEY, strategy TEXT NOT NULL, document_id TEXT NOT NULL, version TEXT NOT NULL,
            source TEXT NOT NULL, page_start INT, page_end INT, printed_page_start INT, chuong TEXT, dieu INT,
            dieu_title TEXT, text TEXT NOT NULL, char_count INT, content_hash TEXT NOT NULL,
            embedding vector({DIM}) NOT NULL)""")
        for strat, n in COUNTS.items():
            for i in range(n):
                c = chunk(strat, i)
                md = c.metadata
                conn.execute(f"INSERT INTO {LEGACY} VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector)",
                             (c.chunk_id, strat, c.document_id, md["version"], c.source, md["page_start"],
                              md["page_end"], md["printed_page_start"], md["chuong"], md["dieu"], md["dieu_title"],
                              c.text, md["char_count"], md["content_hash"], _vec(vec(i + ord(strat)))))
    s.create_schema()
    yield s
    s.drop()
    with s._connect() as conn:
        conn.execute(f"DROP TABLE IF EXISTS {LEGACY}")


def _legacy_count(store):
    with store._connect() as conn:
        return conn.execute(f"SELECT count(*) FROM {LEGACY}").fetchone()[0]


def test_migrate_counts_ids_and_vectors(store):
    result = store.migrate_legacy(LEGACY)
    for strat, n in COUNTS.items():
        assert store.count(strat) == n
        assert result[strat]["legacy"] == n and result[strat]["migrated_total"] == n
        ids = {r["chunk_id"] for r in store.all_chunks(strat)}
        assert ids == {f"{strat}:blld-2019:{i:04d}" for i in range(n)}
    with store._connect() as conn:
        same = conn.execute(
            f"SELECT count(*) FROM {LEGACY} l JOIN chunks_mig_a a USING (chunk_id) WHERE l.embedding = a.embedding"
        ).fetchone()[0]
    assert same == COUNTS["A"]


def test_migrate_idempotent(store):
    store.migrate_legacy(LEGACY)
    store.migrate_legacy(LEGACY)
    assert {s: store.count(s) for s in COUNTS} == COUNTS


def test_legacy_untouched(store):
    before = _legacy_count(store)
    store.migrate_legacy(LEGACY)
    assert _legacy_count(store) == before == sum(COUNTS.values())


def test_migrate_search_order_unchanged(store):
    q = vec(1 + ord("A"))
    with store._connect() as conn:
        expected = [r[0] for r in conn.execute(
            f"SELECT chunk_id FROM {LEGACY} WHERE strategy='A' ORDER BY embedding <=> %s::vector LIMIT 3",
            (_vec(q),)).fetchall()]
    store.migrate_legacy(LEGACY)
    assert [h["chunk_id"] for h in store.search("A", q, top_k=3)] == expected
