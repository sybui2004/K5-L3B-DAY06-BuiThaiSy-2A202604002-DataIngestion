"""CLI: python -m src.run {manifest,ingest,migrate-tables,check-benchmark,evaluate,audit-templates,audit-summary}."""
import argparse
import csv
import hashlib
import json
import logging
import platform
import statistics
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import pymupdf

from . import config
from .audit import coherence_rows, grounding_rows, metadata_rows, summarize_audit, write_rows
from .benchmark import load_questions, validate_questions
from .chunking import by_article, fixed_size
from .embeddings import OllamaEmbedder
from .evaluation import run_strategy, summarize
from .ingest_extra import ingest_extra, length_stats as _length_stats
from .ingestion import load_pdf
from .manifest import write_manifest
from .models import DocumentPage
from .store import PgVectorStore

log = logging.getLogger("day06")


def _setup_logging(results_dir: Path) -> None:
    results_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(results_dir / "errors.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    if not any(isinstance(h, logging.FileHandler) and h.baseFilename == handler.baseFilename for h in log.handlers):
        log.addHandler(handler)
    log.setLevel(logging.INFO)


def load_corpus(max_pages: int | None = None, stats: Counter | None = None) -> dict[str, list[DocumentPage]]:
    pages = {}
    for d in config.DOCUMENTS:
        ps = load_pdf(config.DATA_RAW / d["filename"], d["document_id"], f"data/raw/{d['filename']}",
                      d["version"], stats)
        pages[d["document_id"]] = ps[:max_pages] if max_pages else ps
    return pages


def ingest(max_pages: int | None = None, table: str = "chunks", results_dir: Path = config.RESULTS_DIR) -> dict:
    _setup_logging(results_dir)
    norm = Counter()
    pages = load_corpus(max_pages, norm)
    for doc_id, ps in pages.items():
        for p in ps:
            if not p.metadata["is_content"]:
                log.info("excluded page %s p%s: %s chars", doc_id, p.page, p.metadata["char_count"])
        log.info("normalization %s: split_syllable_suspects=%s", doc_id,
                 sum(p.metadata["split_syllable_suspects"] for p in ps))
    log.info("normalization: glyph_dash_fixed=%s", norm["glyph_dash_fixed"])

    embedder = OllamaEmbedder()
    store = PgVectorStore(config.DATABASE_URL, embedder.dimensions, table=table)
    store.create_schema()
    before = {s: store.count(s) for s in ("A", "B", "C")}
    out = {"strategies": {}}
    for strategy, chunker in (("A", fixed_size), ("B", by_article)):
        t0, embedded, all_chunks = time.perf_counter(), 0, []
        for doc_id, ps in pages.items():
            chunks = chunker(ps)
            known = store.existing_hashes(strategy, doc_id)
            todo = [c for c in chunks if known.get(c.chunk_id) != c.metadata["content_hash"]]
            if todo:
                store.upsert(strategy, todo, embedder.embed_documents([c.text for c in todo]), prune=False)
            removed = store.delete_obsolete(strategy, doc_id, {c.chunk_id for c in chunks})
            log.info("ingest %s %s: %s chunks, %s embedded, %s obsolete removed",
                     strategy, doc_id, len(chunks), len(todo), removed)
            embedded += len(todo)
            all_chunks += chunks
        out["strategies"][strategy] = {"chunk_count": len(all_chunks), "embedded_count": embedded,
                                       "ingest_seconds": round(time.perf_counter() - t0, 1), "cost_usd": 0,
                                       **_length_stats([len(c.text) for c in all_chunks])}
    copied = store.copy_strategy("B", "C")
    out["strategies"]["C"] = {**out["strategies"]["B"], "chunk_count": copied, "embedded_count": 0,
                              "note": "C = copy of B rows (same text, metadata, vectors); differs only by query-time version filter"}
    after = {s: store.count(s) for s in ("A", "B", "C")}
    out["reingest_check"] = {"counts_before": before, "counts_after": after, "same_counts": before == after}
    out["normalization"] = {"glyph_dash_fixed": norm["glyph_dash_fixed"]}
    (results_dir / "ingest_stats.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    with (results_dir / "ingest_history.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"timestamp": datetime.now().isoformat(timespec="seconds"), "max_pages": max_pages,
                             **out}, ensure_ascii=False) + "\n")
    run_info = {"timestamp": datetime.now().isoformat(timespec="seconds"), "python": platform.python_version(),
                "pdf_extractor": f"PyMuPDF {pymupdf.VersionBind}", "embedding": embedder.info(),
                "vector_store": "PostgreSQL 16 + pgvector 0.8.7 (Docker pgvector/pgvector:0.8.7-pg16)",
                "metric": "cosine (<=>), exact search, no ANN index", "table": table, "max_pages": max_pages}
    (results_dir / "run_info.json").write_text(json.dumps(run_info, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def ingest_extra_cmd(strategy: str) -> dict:
    """Ingest an exploration strategy (D/E/F) into its own table; never touches A/B/C or submission files."""
    _setup_logging(config.EXPLORE_DIR)
    embedder = OllamaEmbedder()
    store = PgVectorStore(config.DATABASE_URL, embedder.dimensions)
    store.create_schema()
    return ingest_extra(strategy, store, embedder, load_corpus(), results_dir=config.EXPLORE_DIR)


def _freeze_path(questions_path: Path) -> Path:
    return questions_path.with_name("frozen.json")


def freeze_benchmark(questions_path: Path = config.BENCHMARK_PATH) -> dict:
    """Record the sha256 of the reviewed question file; evaluation refuses to run on any other content."""
    record = {"sha256": hashlib.sha256(questions_path.read_bytes()).hexdigest(),
              "frozen_at": datetime.now().isoformat(timespec="seconds")}
    _freeze_path(questions_path).write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def assert_frozen(questions_path: Path = config.BENCHMARK_PATH) -> None:
    fp = _freeze_path(questions_path)
    if not fp.exists():
        raise SystemExit("benchmark not frozen: review questions, then run `python -m src.run freeze-benchmark`")
    if json.loads(fp.read_text(encoding="utf-8"))["sha256"] != hashlib.sha256(questions_path.read_bytes()).hexdigest():
        raise SystemExit("questions.jsonl changed after freezing; the dev/test split must not change after experiments start")


def evaluate(split: str, results_dir: Path = config.RESULTS_DIR) -> list[dict]:
    assert_frozen()
    questions = [q for q in load_questions(config.BENCHMARK_PATH) if q["split"] == split]
    embedder = OllamaEmbedder()
    store = PgVectorStore(config.DATABASE_URL, embedder.dimensions)
    (results_dir / "traces").mkdir(parents=True, exist_ok=True)
    all_traces = []
    for strategy in ("A", "B", "C"):
        traces = run_strategy(strategy, questions, store, embedder, top_k=config.TOP_K)
        with (results_dir / "traces" / f"{strategy}_{split}.jsonl").open("w", encoding="utf-8") as fh:
            for t in traces:
                fh.write(json.dumps(t, ensure_ascii=False) + "\n")
        all_traces += traces
    metrics_path = results_dir / "metrics.csv"
    rows = {}
    if metrics_path.exists():
        rows = {(r["strategy"], r["split"]): r for r in csv.DictReader(metrics_path.open(encoding="utf-8"))}
    for r in summarize(all_traces):
        r["hit1_n_over_N"], r["hit3_n_over_N"] = f"{r['hit1']}/{r['n']}", f"{r['hit3']}/{r['n']}"
        r["chunk_count"] = store.count(r["strategy"])
        r["evaluated_at"] = datetime.now().isoformat(timespec="seconds")
        rows[(r["strategy"], r["split"])] = r
    fields = ["strategy", "split", "n", "hit1", "hit3", "hit1_n_over_N", "hit3_n_over_N", "chunk_count", "evaluated_at"]
    with metrics_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for key in sorted(rows):
            w.writerow({k: rows[key][k] for k in fields})
    return all_traces


def audit_templates(results_dir: Path = config.RESULTS_DIR) -> None:
    """Write CSVs with empty label columns; never overwrite a file the author may already be grading."""
    audit = results_dir / "audit"
    store = PgVectorStore(config.DATABASE_URL, config.EMBED_DIM)
    targets = {"coherence.csv": lambda: coherence_rows(store, load_corpus())}
    test_files = [results_dir / "traces" / f"{s}_test.jsonl" for s in ("A", "B", "C")]
    if all(f.exists() for f in test_files):
        traces = [json.loads(line) for f in test_files for line in f.read_text(encoding="utf-8").splitlines()]
        expected = {q["id"]: q["expected_answer"] for q in load_questions(config.BENCHMARK_PATH)}
        targets["metadata.csv"] = lambda: metadata_rows(traces)
        targets["grounding.csv"] = lambda: grounding_rows(traces, expected)
    else:
        print("test traces missing: metadata.csv / grounding.csv are created after `evaluate --split test`")
    for name, build in targets.items():
        path = audit / name
        if path.exists():
            print(f"keep existing {path} (delete it to regenerate)")
            continue
        write_rows(path, build())
        print(f"wrote {path}")


def main(argv: list[str] | None = None) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="python -m src.run")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("manifest")
    p_ing = sub.add_parser("ingest")
    p_ing.add_argument("--max-pages", type=int, default=None)
    p_ing.add_argument("--strategy", choices=["D", "E", "F"], default=None,
                       help="ingest an exploration strategy instead of the official A/B/C")
    sub.add_parser("check-benchmark")
    sub.add_parser("freeze-benchmark")
    p_ev = sub.add_parser("evaluate")
    p_ev.add_argument("--split", choices=["dev", "test"], required=True)
    sub.add_parser("migrate-tables")
    sub.add_parser("audit-templates")
    sub.add_parser("audit-summary")
    args = parser.parse_args(argv)
    if args.command == "freeze-benchmark":
        problems = validate_questions(load_questions(config.BENCHMARK_PATH), load_corpus())
        if problems:
            raise SystemExit(f"cannot freeze: {len(problems)} problems; run check-benchmark")
        print(json.dumps(freeze_benchmark(), indent=2))
    elif args.command == "migrate-tables":
        store = PgVectorStore(config.DATABASE_URL, config.EMBED_DIM)
        store.create_schema()
        print(json.dumps(store.migrate_legacy("chunks"), indent=2))
    elif args.command == "audit-templates":
        audit_templates()
    elif args.command == "audit-summary":
        rows = summarize_audit(config.RESULTS_DIR / "audit")
        write_rows(config.RESULTS_DIR / "audit" / "summary.csv", rows)
        for r in rows:
            print(r)
    elif args.command == "evaluate":
        for r in summarize(evaluate(args.split)):
            print(f"{r['strategy']} {r['split']}: Hit@1 {r['hit1']}/{r['n']}  Evidence Hit@3 {r['hit3']}/{r['n']}")
    elif args.command == "manifest":
        write_manifest(load_corpus(), config.MANIFEST_PATH)
        print(f"wrote {config.MANIFEST_PATH}")
    elif args.command == "ingest" and args.strategy:
        print(json.dumps(ingest_extra_cmd(args.strategy), ensure_ascii=False, indent=2))
    elif args.command == "ingest":
        print(json.dumps(ingest(max_pages=args.max_pages), ensure_ascii=False, indent=2))
    elif args.command == "check-benchmark":
        problems = validate_questions(load_questions(config.BENCHMARK_PATH), load_corpus())
        for p in problems:
            print(p)
        print(f"{len(problems)} problems")
        sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
