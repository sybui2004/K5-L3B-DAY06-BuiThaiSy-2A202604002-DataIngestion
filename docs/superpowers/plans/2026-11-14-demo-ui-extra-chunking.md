# Demo UI + Extra Chunking Strategies Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add chunking strategies D (recursive), E (semantic), F (parent-child) and a Streamlit demo app (three-column layout, side-by-side compare, PDF highlight, dev-only benchmark, chunk map, year-filter effect, read-only DB view).

**Architecture:** New chunkers live in `starter/src/chunking_extra.py` and reuse the page-aware helpers of `chunking.py`. A small registry (`src/strategies.py`) is the single list of strategies used by the CLI and the app. The app is a thin Streamlit layer (`starter/app.py`) over testable helper modules in `starter/src/explore/`; it only issues SELECTs. Storage is one table per strategy, with a non-destructive migration of A/B/C from the old `chunks` table. Extra strategies are ingested by a separate command that never touches A/B/C rows or submission artifacts.

**Tech Stack:** Python 3, PostgreSQL 16 + pgvector 0.8.7, Ollama bge-m3 (1024 dims), PyMuPDF, pytest, Streamlit (new; add to `starter/requirements.txt`).

**Spec:** `docs/superpowers/specs/2026-11-14-demo-ui-extra-chunking-design.md`

## Global Constraints

- Only new dependency: `streamlit` (plus a chart lib only if Streamlit's built-ins are insufficient). Same embedder (`bge-m3`, 1024 dims) for every strategy; never mock vectors.
- All commands run from `starter/` with `.venv` active (PowerShell or Git Bash).
- **Do not run `git commit`** (user rule in CLAUDE.md); leave changes in the working tree. If a commit is ever requested: no `Co-Authored-By` line.
- Do not modify: `benchmark/questions.jsonl`, `benchmark/frozen.json`, `assert_frozen`, `results/metrics.csv`, `results/traces/`, `results/audit/`, `results/ingest_stats.json`, `results/run_info.json`, existing rows of the old table `chunks` (read-only source for migration).
- Never run the test split for D/E/F. Exploration output goes only to `results/explore/`.
- DB access from the app is SELECT-only. DB password must never be rendered in the UI.
- Storage is one table per strategy (`chunks_a` ... `chunks_f`, prefix `chunks`); the old table `chunks` is left untouched as a backup. Spec §6.0.
- Existing 51 tests must keep passing; DB/Ollama tests keep their `db` / `ollama` markers.

## Review Focus

1. Empty or whitespace-only question → app shows a prompt, does not call Ollama.
2. Strategy chosen but not ingested (0 rows) → disabled/explained, no crash, no empty-vector query.
3. Ollama or Postgres down at startup → readable message with the start command, no stack trace.
4. Chunk text not locatable on its PDF page (normalisation differences, multi-page chunk) → highlight falls back to "page only" instead of raising.
5. Parent-child: two children of one parent in the same top-3 → parent text shown once per hit, no duplicate-key crash; re-running ingest creates no duplicate rows.

---

### Task 0: One table per strategy and migration of A/B/C

**Files:**
- Modify: `starter/src/store.py`, `starter/src/run.py` (new subcommand `migrate-tables`)
- Test: `starter/tests/test_store.py` (add `db` cases using a throwaway prefix), `starter/tests/test_migrate_tables.py`

**Interfaces:**
- Produces in `PgVectorStore`: `STRATEGY_CODES = "ABCDEF"`; `table_for(strategy: str) -> sql.Identifier` returning `{prefix}_{strategy.lower()}` (constructor keeps `table: str = "chunks"`, which now means *prefix*); `create_schema()` creates all six tables with today's columns, plus `parent_id TEXT, parent_text TEXT` **only in the F table**; every existing method (`existing_hashes`, `upsert`, `delete_obsolete`, `copy_strategy`, `count`, `all_chunks`, `search`) keeps its signature but reads/writes `table_for(strategy)`; `count(None)` sums all six; `drop()` drops the six prefixed tables (never the legacy `chunks`); `upsert` writes `parent_id`/`parent_text` for F and raises `ValueError` for an unknown strategy code; `search` result dicts gain `"parent_text": str | None` (None for non-F). `migrate_legacy(legacy_table: str = "chunks") -> dict[str, dict]` returns per strategy `{"legacy": n, "migrated_total": m}`, copying via `INSERT ... SELECT ... ON CONFLICT (chunk_id) DO NOTHING`; idempotent; never modifies the legacy table; no embedding calls.
- CLI: `python -m src.run migrate-tables` prints that dict as JSON.

- [ ] **Step 1: Write failing tests** (`db` marker, throwaway prefix `t0_<random>`, dropped after each test): `test_each_strategy_has_own_table` (six tables exist; only `_f` has `parent_text`); `test_upsert_goes_to_strategy_table` (upsert B: count B == n, count A == 0); `test_unknown_strategy_rejected`; `test_search_isolated_per_strategy` (same text in A and B, searching "A" returns only ids starting `A:`); `test_copy_strategy_b_to_c`; `test_drop_removes_only_prefixed_tables`. In `test_migrate_tables.py`: build a legacy table with 3 A, 2 B, 2 C rows with distinct vectors; `test_migrate_counts_ids_and_vectors` (new tables hold 3/2/2, identical chunk_ids and vectors); `test_migrate_idempotent`; `test_legacy_untouched` (legacy row count unchanged); `test_migrate_search_order_unchanged` (top-3 ids for a query vector equal the order from the legacy table with the same `ORDER BY embedding <=> q`).
- [ ] **Step 2: Run** `pytest tests/test_store.py tests/test_migrate_tables.py -m db -v` → Expected: new cases FAIL (missing `table_for` / `migrate_legacy`).
- [ ] **Step 3: Implement** the store changes and the `migrate-tables` subcommand; adapt any existing test that hard-codes the single table name to the prefix semantics.
- [ ] **Step 4: Run** `pytest -q` → Expected: the existing 51 tests plus the new ones pass.
- [ ] **Step 5 (real data, Docker up):** record the baseline `SELECT strategy,count(*) FROM chunks GROUP BY 1` (501/505/505) and, using the old table, the top-3 chunk ids for 3 benchmark questions per strategy (throwaway script in the scratchpad, not in the repo); run `python -m src.run migrate-tables`. Expected: `chunks_a/b/c` hold 501/505/505 and the top-3 ids per question and strategy are identical to the baseline. Then a full `python -m src.run ingest` must report `embedded_count: 0` for A and B and `same_counts: true`.

### Task 1: Strategy registry and config constants

**Files:**
- Create: `starter/src/strategies.py`
- Modify: `starter/src/config.py` (append constants)
- Test: `starter/tests/test_strategies.py`

**Interfaces:**
- Produces: `STRATEGIES: dict[str, StrategyInfo]` keyed `"A".."F"`; `StrategyInfo` NamedTuple `(code: str, name: str, description: str, official: bool, filter_by_version: bool)`; `ingested_codes(store) -> list[str]` (codes with `store.count(code) > 0`). Config: `D_SIZE=800`, `D_OVERLAP=100`, `E_SIM_THRESHOLD=0.6`, `E_MAX=1500`, `F_CHILD_SIZE=300`, `EXPLORE_DIR=RESULTS_DIR / "explore"`.

- [ ] **Step 1: Write failing tests** — `test_registry_codes` asserts keys are exactly `list("ABCDEF")`; `test_official_flags` asserts `official` is True only for A,B,C and `filter_by_version` only for C; `test_ingested_codes` uses a stub store with `count` returning `{A:5,B:0,...}` and asserts only non-zero codes are returned in order.
- [ ] **Step 2: Run** `pytest tests/test_strategies.py -v` → FAIL (module missing).
- [ ] **Step 3: Implement** `strategies.py` and the config constants.
- [ ] **Step 4: Run** `pytest tests/test_strategies.py -v` → PASS.

### Task 2: Strategy D — recursive chunker

**Files:**
- Create: `starter/src/chunking_extra.py`
- Test: `starter/tests/test_chunking_recursive.py`

**Interfaces:**
- Consumes: `build_stream`, `structure_at`, `_make_chunk`, `PageSpan` from `src/chunking.py`; `D_SIZE`, `D_OVERLAP`.
- Produces: `recursive(pages: list[DocumentPage], size: int = D_SIZE, overlap: int = D_OVERLAP) -> list[Chunk]` — chunk ids `D:{document_id}:{n:04d}`, `metadata["strategy"] == "D"`, same metadata keys as strategy A.

- [ ] **Step 1: Write failing tests** using `synthetic_pages`: `test_recursive_max_size` (every `len(text) <= size`); `test_recursive_prefers_paragraph_breaks` (with a page whose text has `\n` boundaries, no chunk starts mid-word and ≥1 chunk ends at a `\n` or sentence end); `test_recursive_covers_all_text` (squashed concatenation of chunk texts contains the squashed stream, i.e. nothing lost); `test_recursive_ids_stable_and_hash` (two runs give identical `(chunk_id, content_hash)`; first id is `D:blld-2019:0000`); `test_recursive_page_and_structure_metadata` (last chunk has `dieu == 3`, `chuong == "Chương II"`, `page_start`/`page_end` set).
- [ ] **Step 2: Run** `pytest tests/test_chunking_recursive.py -v` → FAIL.
- [ ] **Step 3: Implement** `recursive`: split the stream by separators in order `["\n\n", "\n", ". ", " "]` (hard cut last), merge pieces up to `size`, apply `overlap` by starting the next chunk `overlap` characters back at a separator boundary when possible. Track stream offsets so `_make_chunk` can compute page span.
- [ ] **Step 4: Run** the file → PASS; then `pytest tests/test_chunking_fixed.py tests/test_chunking_article.py -v` still PASS.

### Task 3: Strategy E — semantic chunker

**Files:**
- Modify: `starter/src/chunking_extra.py`
- Test: `starter/tests/test_chunking_semantic.py`

**Interfaces:**
- Consumes: Task 2 helpers; `E_SIM_THRESHOLD`, `E_MAX`.
- Produces: `semantic(pages, embed: Callable[[list[str]], list[list[float]]], threshold: float = E_SIM_THRESHOLD, max_size: int = E_MAX) -> list[Chunk]` — ids `E:{document_id}:{n:04d}`, `metadata["strategy"] == "E"`. Also `split_sentences(text: str) -> list[tuple[int, int]]` (stream offsets).

- [ ] **Step 1: Write failing tests** with a fake `embed` returning one fixed unit vector for sentences containing "lương" and an orthogonal one otherwise: `test_semantic_cuts_at_topic_change` (a stream "lương…lương…nghỉ…nghỉ…" yields 2 chunks, boundary exactly at the topic change); `test_semantic_respects_max_size` (identical-topic long text still yields chunks `<= max_size`); `test_semantic_embeds_each_sentence_once` (fake counts calls: total inputs == sentence count); `test_semantic_single_sentence_page` (no crash, one chunk); `test_semantic_metadata_and_ids`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** sentence split (reuse the `[.;:]\s+` idea from `_SENTENCE_END`, never split inside an `Điều N.` heading line), embed all sentences of a document in one batched call, cut where cosine similarity of adjacent sentences `< threshold` or accumulated size would exceed `max_size`.
- [ ] **Step 4: Run** → PASS. Note in the plan log: real-data threshold tuning happens in Task 7 Step 4 and the final value is recorded in `config.py`.

### Task 4: Strategy F — parent-child chunker and store support

**Files:**
- Modify: `starter/src/chunking_extra.py`
- Test: `starter/tests/test_chunking_parent_child.py`, `starter/tests/test_store.py` (add F cases, `db` marker)

**Interfaces:**
- Consumes: `by_article` (parents), `F_CHILD_SIZE`.
- Produces: `parent_child(pages, child_size: int = F_CHILD_SIZE) -> list[Chunk]` — child ids `F:{document_id}:d{dieu:03d}-p{part}-c{n:02d}`, `metadata["strategy"] == "F"`, `metadata["parent_id"]` = the B chunk id it came from, `metadata["parent_text"]` = that B chunk's text; each child `len(text) <= child_size` and its text is a substring of its parent's text. Storage of `parent_id`/`parent_text` comes from Task 0 (table `chunks_f`).

- [ ] **Step 1: Write failing tests** — chunker: `test_children_within_size_and_inside_parent`; `test_children_cover_parent` (squashed children concatenated contain the squashed parent minus header duplication — assert no parent text lost); `test_child_parent_fields_present`; `test_child_ids_unique_and_stable`. Store (db): `test_f_upsert_and_search_returns_parent_text`, `test_non_f_search_has_parent_text_none`.
- [ ] **Step 2: Run** `pytest tests/test_chunking_parent_child.py -v` → FAIL; `pytest tests/test_store.py -m db -v` → new cases FAIL (needs Docker up).
- [ ] **Step 3: Implement** the chunker; splitting children uses the existing clause/sentence helpers (`_pieces`, `_fit`) from `chunking.py`.
- [ ] **Step 4: Run** all three test files plus `tests/test_chunking_article.py` → PASS (existing store tests must stay green).

### Task 5: Ingest command for D/E/F

**Files:**
- Create: `starter/src/ingest_extra.py`
- Modify: `starter/src/run.py` (`ingest` subparser gets `--strategy {D,E,F}`; default behavior unchanged)
- Test: `starter/tests/test_ingest_extra.py`

**Interfaces:**
- Consumes: Tasks 1–4; `load_corpus`, `OllamaEmbedder`, `PgVectorStore` (`existing_hashes`, `upsert`, `delete_obsolete`).
- Produces: `ingest_extra(strategy: str, store, embedder, pages_by_doc: dict, results_dir: Path = EXPLORE_DIR) -> dict` returning `{"strategy", "chunk_count", "embedded_count", "ingest_seconds", "len_min", "len_mean", "len_p50", "len_p95", "len_max"}` and writing `results/explore/ingest_{strategy}.json`. Chunker lookup: D → `recursive`, E → `semantic(pages, embedder.embed_documents)`, F → `parent_child`. Raises `ValueError` for A/B/C.

- [ ] **Step 1: Write failing tests** with in-memory fake store/embedder: `test_ingest_embeds_only_new_or_changed` (second call → `embedded_count == 0`); `test_ingest_rejects_official_strategies`; `test_ingest_never_touches_other_strategies` (fake store records `strategy` args; none equal A/B/C); `test_ingest_writes_only_under_results_dir` (tmp dir passed; `results/ingest_stats.json` untouched); `test_cli_default_ingest_unchanged` (argparse: no `--strategy` still routes to the old `ingest`).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** `ingest_extra` mirroring the per-document loop in `run.ingest` (hash diff → embed todo → upsert → `delete_obsolete`), and wire the CLI flag.
- [ ] **Step 4: Run** `pytest tests/test_ingest_extra.py tests/test_run_ingest.py -v` → PASS.
- [ ] **Step 5 (real data):** with Docker + Ollama up run `python -m src.run ingest --strategy D`, then `E`, then `F`. Expected: each prints stats; rerun prints `embedded_count: 0`; `SELECT count(*)` on `chunks_a/b/c` is unchanged at 501/505/505 and `chunks_d/e/f` are > 0.

### Task 6: Explore helpers (pure, no Streamlit)

**Files:**
- Create: `starter/src/explore/__init__.py`, `health.py`, `pdf_view.py`, `chunk_map.py`, `bench.py`
- Test: `starter/tests/test_explore_pdf_view.py`, `test_explore_chunk_map.py`, `test_explore_bench.py`, `test_explore_health.py`

**Interfaces:**
- `health.check_services(database_url: str, ollama_url: str, model: str) -> dict[str, str | None]` → `{"postgres": None | error_message, "ollama": None | error_message}`; `None` means healthy; messages include the start command (`docker compose up -d` / `ollama pull bge-m3`); never raises.
- `pdf_view.render_page(pdf_path: Path, page: int, highlight_text: str | None, zoom: float = 1.5) -> tuple[bytes, str]` → (PNG bytes, note). Highlight by locating the leading and trailing ~60 squashed chars of the chunk on that page (PyMuPDF `search_for` on the original text lines); note is `""` when highlighted, `"không định vị được đoạn trên trang"` when not found, and mentions remaining pages when the chunk spans several. Never raises for a missing text.
- `chunk_map.page_rows(chunks: list[dict]) -> list[dict]` → rows `{"chunk_id", "page_start", "page_end", "char_count", "dieu"}` sorted by page then id; `length_histogram(chunks, bins: int = 10) -> list[tuple[int, int]]`.
- `bench.run_explore_benchmark(strategy: str, questions: list[dict], store, embedder, out_dir: Path = EXPLORE_DIR) -> list[dict]` → calls `assert_frozen()` first, **raises `ValueError` unless every question has `split == "dev"`**, writes `out_dir/traces/{strategy}_dev.jsonl` and `out_dir/metrics.csv` (strategy, n, hit1, hit3); never writes under `RESULTS_DIR` root. Uses `run_strategy` and `summarize`.

- [ ] **Step 1: Write failing tests** — pdf_view: `test_highlight_found` (use a tiny PDF generated with PyMuPDF in `tmp_path`, assert PNG header `b"\x89PNG"` and empty note); `test_highlight_text_not_on_page` (returns PNG + the fallback note); `test_none_highlight_ok`. chunk_map: `test_rows_sorted`, `test_histogram_counts_sum_to_n`, `test_histogram_empty_list_ok`. bench: `test_rejects_test_split`, `test_requires_frozen` (monkeypatch `assert_frozen` to raise `SystemExit`; assert it propagates and nothing is written), `test_writes_only_in_out_dir`, `test_metrics_match_summarize`. health: `test_unreachable_hosts_return_messages_not_exceptions` (closed port URLs).
- [ ] **Step 2: Run** the four files → FAIL.
- [ ] **Step 3: Implement** the four modules per the interfaces above.
- [ ] **Step 4: Run** the four files → PASS.

### Task 7: Streamlit app

**Files:**
- Create: `starter/app.py`, `starter/src/explore/services.py`
- Modify: `starter/requirements.txt` (add `streamlit>=1.40,<2`)
- Test: `starter/tests/test_app_smoke.py` (uses `streamlit.testing.v1.AppTest`)

**Interfaces:**
- `services.get_services() -> Services` (dataclass: `store`, `embedder`, `pages_by_doc`, `health`), wrapped in `st.cache_resource`; the app imports it as a module attribute so tests can monkeypatch it with stubs.
- Layout (spec §6.2): sidebar-free, one page. Left column: strategy radio/multiselect from `STRATEGIES` with chunk counts and "chưa nạp — chạy `python -m src.run ingest --strategy X`" for empty ones; year filter (`Tất cả/2019/2012`); "So sánh song song" multiselect. Middle: question box, sample-question selectbox (all 20 from benchmark, picking one fills the box), "Truy xuất top-3" button, results with rank/Điều/trang/score/text and ✅ when `is_hit` and the sample question is selected; compare mode renders one column per selected strategy; F shows `parent_text` in an expander. Right: PDF page image from `pdf_view.render_page` for the selected result, score bar chart, metadata table. Tabs below: **Benchmark** (dev run button per ingested strategy, table of `results/explore/metrics.csv`, expandable failing questions; test numbers A/B/C read-only from `results/metrics.csv`), **Bản đồ chunk** (rows + histogram per strategy), **Bộ lọc năm** (same question with/without `filters={"version": …}`), **Dữ liệu DB** (counts per strategy table, 20 sample rows without the embedding column, the equivalent SQL (`SELECT ... FROM chunks_b ...`), DBeaver settings: host 127.0.0.1, port 55433, db `day6_lab`, user `day6`, "mật khẩu: xem `starter/.env`").
- Year filter applies only when the user chose a year; filters use `PgVectorStore.search(..., filters={"version": v})`.

- [ ] **Step 1: Write failing smoke tests** with stub services: `test_app_loads_without_error`; `test_empty_question_shows_prompt_and_makes_no_embed_call` (stub counts `embed_query` calls == 0); `test_unavailable_services_show_message` (stub health returns errors → `at.error` present, no exception); `test_not_ingested_strategy_is_disabled_with_command` (stub count 0 for D → page text contains `ingest --strategy D`); `test_search_calls_store_with_version_filter` (choose 2019 → stub store received `filters={"version": "2019"}`).
- [ ] **Step 2: Run** `pytest tests/test_app_smoke.py -v` → FAIL.
- [ ] **Step 3: Implement** `app.py` and `services.py`; add the dependency and `pip install -r requirements.txt`.
- [ ] **Step 4 (tune E, real data):** run the app, query three benchmark questions on E, look at the chunk map/histogram; adjust `E_SIM_THRESHOLD` / `E_MAX` in `config.py` only if E yields obviously degenerate chunks (many < 100 chars or a few near `E_MAX`); re-run `ingest --strategy E` after any change and record the final values in the plan log.
- [ ] **Step 5: Run** `pytest tests/test_app_smoke.py -v` → PASS.
- [ ] **Step 6 (manual demo check, Docker + Ollama up):** `streamlit run app.py`; confirm: one sample question on A, B, C, D, E, F each shows 3 results; toggling 2012/2019 changes C results; the PDF page shows a highlight for B; dev benchmark button writes `results/explore/metrics.csv`; A/B/C numbers in the Benchmark tab equal `results/metrics.csv`; DB tab lists the six tables with counts and no password; stopping Ollama then reloading shows the readable message.

### Task 8: Docs and final verification

**Files:**
- Modify: `starter/README.md` (how to run the app, ingest D/E/F, DBeaver connection steps, a note on the six `chunks_*` tables)
- Test: none new

- [ ] **Step 1: Document** the three commands (`ingest --strategy D|E|F`, `streamlit run app.py`, DBeaver connection) and the `results/explore/` vs `results/` distinction.
- [ ] **Step 2: Run the full suite** `pytest -q` (Docker + Ollama up). Expected: all existing 51 plus new tests pass; no skips except unmarked-environment ones.
- [ ] **Step 3: Confirm protected artifacts untouched:** `git status --short results benchmark` shows no modification to `metrics.csv`, `traces/`, `audit/`, `ingest_stats.json`, `run_info.json`, `benchmark/questions.jsonl`, `benchmark/frozen.json` caused by this work (new files only under `results/explore/`); `python -m src.run evaluate --split dev` still refuses if `questions.jsonl` is altered (existing test `tests/test_benchmark.py` / `test_run_ingest.py` cover this).
- [ ] **Step 4:** Report results to the user. Do not commit.
