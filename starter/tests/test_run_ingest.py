import pytest

from src import config
from src.run import ingest
from src.store import PgVectorStore

pytestmark = [pytest.mark.ollama, pytest.mark.db]


def test_ingest_twice_no_duplicates(tmp_path):
    table = "chunks_ingest_test"
    try:
        first = ingest(max_pages=3, table=table, results_dir=tmp_path)
        second = ingest(max_pages=3, table=table, results_dir=tmp_path)
        for s in ("A", "B", "C"):
            assert first["strategies"][s]["chunk_count"] == second["strategies"][s]["chunk_count"] > 0
        assert second["strategies"]["A"]["embedded_count"] == 0
        assert second["strategies"]["B"]["embedded_count"] == 0
        assert second["reingest_check"]["same_counts"] is True
        assert (tmp_path / "ingest_stats.json").exists() and (tmp_path / "run_info.json").exists()
        history = (tmp_path / "ingest_history.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(history) == 2
    finally:
        PgVectorStore(config.DATABASE_URL, config.EMBED_DIM, table=table).drop()
