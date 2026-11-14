"""PostgreSQL + pgvector store: one table per strategy, idempotent upsert, exact cosine search, version filter."""
from typing import Any

import psycopg
from psycopg import sql

from .config import TOP_K
from .models import Chunk

ALLOWED_FILTERS = {"version"}
STRATEGY_CODES = "ABCDEF"
META_COLS = ["document_id", "version", "source", "page_start", "page_end", "printed_page_start",
             "chuong", "dieu", "dieu_title", "char_count", "content_hash"]
PARENT_COLS = ["parent_id", "parent_text"]  # only the F (parent-child) table has them


def _vec(v: list[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in v) + "]"


class PgVectorStore:
    """`table` is a name prefix: strategy B lives in `{table}_b` (default `chunks_b`)."""

    def __init__(self, database_url: str, dimensions: int, table: str = "chunks") -> None:
        if not database_url:
            raise ValueError("DATABASE_URL is empty; copy starter/.env.example to starter/.env")
        self.database_url = database_url
        self.dimensions = dimensions
        self.prefix = table

    def table_for(self, strategy: str) -> sql.Identifier:
        if strategy not in STRATEGY_CODES or len(strategy) != 1:
            raise ValueError(f"unknown strategy {strategy!r}; expected one of {list(STRATEGY_CODES)}")
        return sql.Identifier(f"{self.prefix}_{strategy.lower()}")

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self.database_url, autocommit=True)

    def create_schema(self) -> None:
        """One table per strategy. Exact search only: no ANN index (~500 vectors per table)."""
        with self._connect() as conn:
            conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            for code in STRATEGY_CODES:
                extra = sql.SQL("parent_id TEXT, parent_text TEXT, ") if code == "F" else sql.SQL("")
                conn.execute(sql.SQL("""CREATE TABLE IF NOT EXISTS {} (
                    chunk_id TEXT PRIMARY KEY, strategy TEXT NOT NULL, document_id TEXT NOT NULL,
                    version TEXT NOT NULL, source TEXT NOT NULL, page_start INT, page_end INT,
                    printed_page_start INT, chuong TEXT, dieu INT, dieu_title TEXT, {} text TEXT NOT NULL,
                    char_count INT, content_hash TEXT NOT NULL, embedding vector({}) NOT NULL)""").format(
                    self.table_for(code), extra, sql.Literal(self.dimensions)))

    def drop(self) -> None:
        """Drop the prefixed strategy tables only (never a legacy single table)."""
        with self._connect() as conn:
            for code in STRATEGY_CODES:
                conn.execute(sql.SQL("DROP TABLE IF EXISTS {}").format(self.table_for(code)))

    def existing_hashes(self, strategy: str, document_id: str) -> dict[str, str]:
        with self._connect() as conn:
            rows = conn.execute(sql.SQL("SELECT chunk_id, content_hash FROM {} WHERE strategy=%s AND document_id=%s")
                                .format(self.table_for(strategy)), (strategy, document_id)).fetchall()
        return dict(rows)

    def upsert(self, strategy: str, chunks: list[Chunk], vectors: list[list[float]], prune: bool = True) -> dict:
        """Insert/update `chunks`; with prune=True also delete rows of the same documents that are not in `chunks`."""
        table = self.table_for(strategy)
        if len(chunks) != len(vectors):
            raise ValueError(f"{len(chunks)} chunks but {len(vectors)} vectors")
        if any(len(v) != self.dimensions for v in vectors):
            raise ValueError(f"every vector must have {self.dimensions} dimensions")
        parent = PARENT_COLS if strategy == "F" else []
        cols = ["chunk_id", "strategy"] + META_COLS + parent + ["text", "embedding"]
        stmt = sql.SQL("INSERT INTO {} ({}) VALUES ({}) ON CONFLICT (chunk_id) DO UPDATE SET {}").format(
            table, sql.SQL(",").join(map(sql.Identifier, cols)),
            sql.SQL(",").join([sql.Placeholder()] * (len(cols) - 1) + [sql.SQL("%s::vector")]),
            sql.SQL(",").join(sql.SQL("{0}=EXCLUDED.{0}").format(sql.Identifier(c)) for c in cols[1:]))
        rows = [[c.chunk_id, strategy, c.document_id, c.metadata["version"], c.source]
                + [c.metadata.get(k) for k in META_COLS[3:]] + [c.metadata.get(k) for k in parent]
                + [c.text, _vec(v)]
                for c, v in zip(chunks, vectors)]
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.executemany(stmt, rows)
        deleted = sum(self.delete_obsolete(strategy, doc, {c.chunk_id for c in chunks if c.document_id == doc})
                      for doc in {c.document_id for c in chunks}) if prune else 0
        return {"upserted": len(rows), "deleted": deleted}

    def delete_obsolete(self, strategy: str, document_id: str, keep: set[str]) -> int:
        """Remove rows of (strategy, document) whose chunk_id is not in `keep` (re-ingest of a changed document)."""
        with self._connect() as conn:
            return conn.execute(sql.SQL(
                "DELETE FROM {} WHERE strategy=%s AND document_id=%s AND NOT (chunk_id = ANY(%s))").format(
                self.table_for(strategy)), (strategy, document_id, list(keep))).rowcount

    def copy_strategy(self, src: str, dst: str) -> int:
        """Copy the shared columns of every `src` row into `dst` (ids re-prefixed), replacing dst's rows."""
        cols = ["strategy"] + META_COLS + ["text", "embedding"]
        with self._connect() as conn:
            conn.execute(sql.SQL("DELETE FROM {}").format(self.table_for(dst)))
            return conn.execute(sql.SQL(
                "INSERT INTO {dst} (chunk_id, {cols}) SELECT %s || substr(chunk_id, length(%s) + 1), %s, {rest} "
                "FROM {src}").format(
                dst=self.table_for(dst), src=self.table_for(src),
                cols=sql.SQL(",").join(map(sql.Identifier, cols)),
                rest=sql.SQL(",").join(map(sql.Identifier, cols[1:]))),
                (f"{dst}:", f"{src}:", dst)).rowcount

    def count(self, strategy: str | None = None) -> int:
        codes = STRATEGY_CODES if strategy is None else strategy
        with self._connect() as conn:
            return sum(conn.execute(sql.SQL("SELECT count(*) FROM {}").format(self.table_for(c))).fetchone()[0]
                       for c in codes)

    def all_chunks(self, strategy: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(sql.SQL("SELECT chunk_id, text, {} FROM {} ORDER BY chunk_id").format(
                sql.SQL(",").join(map(sql.Identifier, META_COLS)), self.table_for(strategy))).fetchall()
        return [{"chunk_id": r[0], "text": r[1], "metadata": dict(zip(META_COLS, r[2:]))} for r in rows]

    def sample_rows(self, strategy: str, limit: int = 20) -> list[dict[str, Any]]:
        """First `limit` rows of a strategy table without the embedding column (read-only inspection)."""
        cols = ["chunk_id", "strategy"] + META_COLS + ["text"]
        with self._connect() as conn:
            rows = conn.execute(sql.SQL("SELECT {} FROM {} ORDER BY chunk_id LIMIT %s").format(
                sql.SQL(",").join(map(sql.Identifier, cols)), self.table_for(strategy)), (limit,)).fetchall()
        return [dict(zip(cols, r)) for r in rows]

    def search(self, strategy: str, query_vector: list[float], top_k: int = TOP_K,
               filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        filters = filters or {}
        bad = set(filters) - ALLOWED_FILTERS
        if bad:
            raise ValueError(f"unsupported filter keys: {sorted(bad)}")
        where = [sql.SQL("strategy = %s")] + [sql.SQL("{} = %s").format(sql.Identifier(k)) for k in filters]
        parent = sql.SQL("parent_text") if strategy == "F" else sql.SQL("NULL::text")
        q = _vec(query_vector)
        stmt = sql.SQL("SELECT chunk_id, text, 1 - (embedding <=> %s::vector) AS score, {}, {} FROM {} "
                       "WHERE {} ORDER BY embedding <=> %s::vector LIMIT %s").format(
            parent, sql.SQL(",").join(map(sql.Identifier, META_COLS)), self.table_for(strategy),
            sql.SQL(" AND ").join(where))
        with self._connect() as conn:
            rows = conn.execute(stmt, [q, strategy, *filters.values(), q, top_k]).fetchall()
        return [{"chunk_id": r[0], "text": r[1], "score": float(r[2]), "parent_text": r[3],
                 "metadata": dict(zip(META_COLS, r[4:]))} for r in rows]

    def migrate_legacy(self, legacy_table: str = "chunks") -> dict[str, dict]:
        """Copy rows of the old single table into the per-strategy tables; legacy table is only read."""
        legacy = sql.Identifier(legacy_table)
        cols = ["chunk_id", "strategy"] + META_COLS + ["text", "embedding"]
        col_list = sql.SQL(",").join(map(sql.Identifier, cols))
        out = {}
        with self._connect() as conn:
            for code in STRATEGY_CODES:
                n = conn.execute(sql.SQL("SELECT count(*) FROM {} WHERE strategy=%s").format(legacy),
                                 (code,)).fetchone()[0]
                if n:
                    conn.execute(sql.SQL("INSERT INTO {} ({}) SELECT {} FROM {} WHERE strategy=%s "
                                         "ON CONFLICT (chunk_id) DO NOTHING").format(
                        self.table_for(code), col_list, col_list, legacy), (code,))
                out[code] = {"legacy": n,
                             "migrated_total": conn.execute(sql.SQL("SELECT count(*) FROM {}").format(
                                 self.table_for(code))).fetchone()[0]}
        return out
