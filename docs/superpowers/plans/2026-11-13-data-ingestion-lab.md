# Day 06 Data Ingestion Lab — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pipeline Python ingest Bộ luật Lao động 2012 & 2019 vào pgvector, so sánh 3 chiến lược A/B/C trên benchmark 20 câu, xuất trace, chỉ số, mẫu audit và báo cáo theo rubric Day 06.

**Architecture:** PDF → `DocumentPage` đã chuẩn hóa → dòng chảy văn bản theo tài liệu (giữ offset→trang) → chunk A (cố định) / B (theo Điều) → embed `bge-m3` qua Ollama → bảng `chunks` trong PostgreSQL+pgvector (C = bản chép dòng của B) → truy xuất top-3 cosine exact, C thêm `WHERE version` khi câu hỏi có filter → chấm Hit@1/Hit@3 tự động + CSV audit để người chấm.

**Tech Stack:** Python 3.11, pypdf (hoặc PyMuPDF nếu Task 2 chứng minh tốt hơn), psycopg 3, PostgreSQL 16 + pgvector 0.8 (Docker), Ollama 0.40.16 + `bge-m3`, pytest, stdlib `urllib`/`json`/`csv`.

**Spec:** `docs/superpowers/specs/2026-11-13-data-ingestion-lab-design.md`

## Global Constraints

- Code ở `starter/src/`, test ở `starter/tests/`, chạy mọi lệnh từ `starter/` với venv `.venv` đã kích hoạt.
- Data/benchmark/results tính từ root repo: `data/raw/`, `data/manifest.csv`, `benchmark/questions.jsonl`, `results/`, `artifacts/experiment_log.csv`.
- `document_id`: `blld-2012`, `blld-2019`; `version`: `"2012"`, `"2019"` (chuỗi).
- Embedding: `bge-m3`, 1024 chiều, `POST http://localhost:11434/api/embed`, không tiền tố query/document.
- A: 800 ký tự, overlap 100. B: tối đa 1.500 ký tự/chunk. Trang nội dung: ≥ 200 ký tự sau chuẩn hóa. Evidence tối thiểu 30 ký tự (sau bỏ khoảng trắng).
- Metric cosine, exact search, **không** tạo index ANN. Top-k = 3.
- Không bao giờ fallback sang vector giả; lỗi Ollama/DB → raise và dừng.
- **Không tự `git commit`** — mỗi "Điểm commit" là chỗ dừng để người dùng tự commit (user rule trong CLAUDE.md). Không commit `.env`, `.venv`.
- Không điền nhãn audit; không tạo số liệu chưa chạy.

## Review Focus

1. Ollama tắt hoặc chưa `pull bge-m3` → phải raise `EmbeddingBackendError` có hướng dẫn, không trả vector → test ở Task 5.
2. Nạp lại sau khi đổi tham số chunk → chunk cũ của (strategy, document) phải bị xóa, số dòng khớp lần nạp mới → test ở Task 6.
3. Câu hỏi có filter với giá trị không tồn tại (vd `"2020"`) hoặc filter không do câu hỏi nêu → validator báo lỗi trước khi chạy → test ở Task 8.
4. Evidence người dùng gõ sạch ("người sử dụng") nhưng PDF có lỗi tách âm tiết ("ng ười s ử dụng") → vẫn phải là hit → test ở Task 9.
5. Trang rỗng (2019 trang 94) và khoản đơn lẻ > 1.500 ký tự → không crash, trang rỗng ghi log, khoản dài tách theo câu → test ở Task 2 và Task 4.

---

### Task 1: Môi trường, corpus và cấu hình

**Files:**
- Create: `data/raw/blld_2012_congbao.pdf`, `data/raw/blld_2019_congbao.pdf` (chép từ `C:\Users\admin\AppData\Local\Temp\claude\bb9d2234825f6a59\abc80f6b-3403-4714-aeb0-57de24788140\scratchpad\dl\blld2012_congbao.pdf` và `...\blld2019_congbao.pdf`; nếu scratchpad đã mất, tải lại từ link trong spec §4)
- Create: `starter/src/config.py`, `starter/tests/__init__.py`, `starter/tests/test_config.py`
- Modify: `starter/requirements.txt` (thêm `pytest>=8,<9`)

**Interfaces:**
- Produces (`src/config.py`): `REPO_ROOT: Path`, `DATA_RAW`, `MANIFEST_PATH`, `BENCHMARK_PATH`, `RESULTS_DIR`, `EXPERIMENT_LOG`; `DOCUMENTS: list[dict]` với khóa `document_id, filename, version, title, source_url`; hằng `EMBED_MODEL="bge-m3"`, `OLLAMA_URL` (từ env, mặc định `http://localhost:11434`), `EMBED_DIM=1024`, `A_SIZE=800`, `A_OVERLAP=100`, `B_MAX=1500`, `MIN_PAGE_CHARS=200`, `MIN_EVIDENCE_CHARS=30`, `TOP_K=3`, `COHERENCE_PAGES=(5,15,25,35,45)`, `DATABASE_URL` (từ `.env`).

- [ ] **Step 1:** Tạo venv, cài requirements, `Copy-Item .env.example .env`, `docker compose -p day6_student_starter up -d --wait`, `python scripts/check_setup.py` → thấy `Setup OK`.
- [ ] **Step 2:** `ollama pull bge-m3` rồi `ollama list` → có dòng `bge-m3`; ghi digest lại cho Task 7.
- [ ] **Step 3:** Chép 2 PDF vào `data/raw/`.
- [ ] **Step 4: Write test** `test_documents_exist_and_versions` — với mỗi phần tử `DOCUMENTS`: `(DATA_RAW / d["filename"]).exists()`, `d["version"] in {"2012","2019"}`, `document_id` duy nhất.
- [ ] **Step 5:** `python -m pytest tests/test_config.py -v` → FAIL (chưa có config) → viết `config.py` → PASS.
- [ ] **Điểm commit** (người dùng): `chore: add corpus PDFs and config`.

### Task 2: Đọc PDF, chuẩn hóa, manifest

**Files:**
- Modify: `starter/src/ingestion.py`
- Create: `starter/tests/test_ingestion.py`, `starter/src/manifest.py`

**Interfaces:**
- Produces:
  - `normalize_text(text: str, stats: Counter | None = None) -> str` — NFC, sửa glyph an toàn, gộp khoảng trắng thừa trong dòng, giữ xuống dòng; tăng `stats["glyph_dash_fixed"]`.
  - `strip_gazette_header(text: str) -> tuple[str, int | None]` — bỏ dòng `CÔNG BÁO/Số …`, trả số trang in.
  - `load_pdf(path: Path, document_id: str, source: str, version: str) -> list[DocumentPage]` — một `DocumentPage` mỗi trang vật lý (page 1-based), `metadata` gồm `version`, `printed_page`, `is_content` (≥ `MIN_PAGE_CHARS`), `split_syllable_suspects` (int).
  - `write_manifest(pages_by_doc: dict[str, list[DocumentPage]], path: Path) -> None` trong `manifest.py` — cột theo spec §4 (`source_id, title, source_url, license_or_permission, accessed_at, physical_pages, counted_pages, excluded_pages, char_count, sha256, gazette_issue, effective_date_from_text`).

- [ ] **Step 1: Write tests**
  - `test_glyph_fix_only_in_safe_context`: `normalize_text("Ngày 05ộ8ộ2012")` chứa `"05-8-2012"`; `normalize_text("Độc lập Ị Tự do Ị Hạnh phúc")` == `"Độc lập - Tự do - Hạnh phúc"`; `normalize_text("người lao động")` == `"người lao động"` (không đụng `ộ` hợp lệ).
  - `test_strip_header_returns_printed_page`: `" CÔNG BÁO/Số 993 + 994/Ngày 26-12-2019 43 \nĐiều 95. Trả lương"` → text bắt đầu `"Điều 95."`, printed_page `43`; header dạng `"4 CÔNG BÁO/Số …"` (số trang đứng trước) → `4`.
  - `test_nfc`: chuỗi NFD → kết quả là NFC.
  - `test_load_real_pdfs` (dùng file thật): 2012 có 83 trang, 2019 có 94 trang; trang 94 của 2019 có `is_content == False`; trang 1 của 2019 chứa `"Điều 1. Phạm vi điều chỉnh"`; không trang nào còn chứa `"CÔNG BÁO/Số"`.
- [ ] **Step 2:** Chạy `python -m pytest tests/test_ingestion.py -v` → FAIL.
- [ ] **Step 3:** Hiện thực các hàm trên. Đếm `split_syllable_suspects` bằng heuristic số token 1–2 ký tự chữ thường đứng sát nhau (chỉ để đo, không sửa).
- [ ] **Step 4:** So sánh pypdf vs PyMuPDF trên bản 2019 (tổng `split_syllable_suspects`); chọn thư viện ít lỗi hơn, ghi lý do và con số vào `results/errors.log` (mục `extractor_choice`). Nếu đổi sang PyMuPDF thì thêm `pymupdf` vào requirements.
- [ ] **Step 5:** Chạy lại test → PASS.
- [ ] **Step 6:** Ngày hiệu lực: đọc điều khoản hiệu lực cuối mỗi văn bản (2012: Điều 241–242 vùng cuối; 2019: điều "Hiệu lực thi hành"), điền `effective_date_from_text` thủ công từ chính văn bản. Chạy `python -m src.run manifest` (lệnh thêm ở Task 7, tạm gọi `write_manifest` trực tiếp) → `data/manifest.csv` có 2 dòng, `counted_pages` 2012 = 83, 2019 = 93.
- [ ] **Điểm commit:** `feat: PDF ingestion, normalization and manifest`.

### Task 3: Dòng chảy văn bản và chunking A

**Files:**
- Modify: `starter/src/chunking.py`, `starter/src/models.py` (không đổi field; chỉ docstring liệt kê khóa metadata)
- Create: `starter/tests/test_chunking_fixed.py`

**Interfaces:**
- Consumes: `DocumentPage` từ Task 2.
- Produces:
  - `build_stream(pages: list[DocumentPage]) -> tuple[str, list[PageSpan]]` với `PageSpan = NamedTuple(start:int, end:int, page:int, printed_page:int|None)`; chỉ trang `is_content`; ngăn trang bằng `"\n"`.
  - `pages_for_span(spans, start, end) -> tuple[int, int, int | None]` → `(page_start, page_end, printed_page_start)`.
  - `structure_at(stream: str, offset: int) -> tuple[str | None, int | None, str | None]` → `(chuong, dieu, dieu_title)` gần nhất trước offset.
  - `fixed_size(pages: list[DocumentPage], size: int = A_SIZE, overlap: int = A_OVERLAP) -> list[Chunk]` — `chunk_id = f"A:{document_id}:{i:04d}"`, `Chunk.page = page_start`, metadata: `strategy="A"`, `version`, `page_start`, `page_end`, `printed_page_start`, `chuong`, `dieu`, `dieu_title`, `char_count`, `content_hash` (sha256 hex của text).

- [ ] **Step 1: Write tests** (dữ liệu tổng hợp 3 trang ~600 ký tự/trang, có `"Chương I\n…\nĐiều 1. A\n…\nĐiều 2. B"`):
  - `test_fixed_sizes_and_overlap`: mọi chunk `len(text) <= 800`; với i>0, `chunks[i].text[:100] == chunks[i-1].text[-100:]`.
  - `test_fixed_page_span`: chunk bắt đầu ở trang 1 và kết thúc ở trang 2 có `page_start==1`, `page_end==2`.
  - `test_fixed_structure_metadata`: chunk bắt đầu sau `"Điều 2."` có `dieu==2`, `chuong=="Chương I"`.
  - `test_fixed_ids_stable`: gọi 2 lần → cùng danh sách `chunk_id` và `content_hash`.
- [ ] **Step 2:** `python -m pytest tests/test_chunking_fixed.py -v` → FAIL → hiện thực → PASS.
- [ ] **Điểm commit:** `feat: page-aware stream and fixed-size chunking`.

### Task 4: Chunking B theo Điều

**Files:**
- Modify: `starter/src/chunking.py` (thay `by_paragraph` bằng `by_article`)
- Create: `starter/tests/test_chunking_article.py`

**Interfaces:**
- Consumes: `build_stream`, `pages_for_span` (Task 3).
- Produces: `by_article(pages: list[DocumentPage], max_size: int = B_MAX) -> list[Chunk]` — `chunk_id = f"B:{document_id}:d{dieu:03d}-p{part}"`; metadata giống A với `strategy="B"`.

Thuật toán (không suy ra được từ test): tách tại đầu dòng khớp `^Điều\s+\d+\.`; phần trước Điều 1 và dòng `Chương …`/`Mục …` không thành chunk, chỉ cập nhật metadata. Điều ≤ `max_size` → 1 chunk. Điều dài: header = dòng đầu `Điều X. Tên`; gom các khoản (đầu dòng `^\d+\.\s`) liên tiếp sao cho `len(header + "\n" + phần) <= max_size`; khoản đơn lẻ vẫn quá → tách theo câu (`(?<=[.;:])\s+`), mỗi phần vẫn có header.

- [ ] **Step 1: Write tests**
  - `test_one_chunk_per_short_article`: 3 Điều ngắn → 3 chunk, `dieu == [1,2,3]`, mỗi text bắt đầu bằng `"Điều "`.
  - `test_preamble_and_chapter_not_chunks`: không chunk nào bắt đầu bằng `"Căn cứ"` hay `"Chương"`; chunk Điều 1 có `chuong == "Chương I"`.
  - `test_long_article_split_by_clause`: Điều 5 gồm 4 khoản × 600 ký tự → ≥ 2 chunk, mọi chunk `len <= 1500`, mọi chunk bắt đầu `"Điều 5. "`, nối các phần (bỏ header) chứa đủ cả 4 khoản theo thứ tự.
  - `test_single_huge_clause_split_by_sentence`: 1 khoản 3.200 ký tự gồm nhiều câu → mọi chunk `len <= 1500`, không mất câu nào.
  - `test_real_2019_article_count`: trên PDF 2019 thật, tập `dieu` của B bao phủ 1..220 (Bộ luật 2019 có 220 Điều) — nếu thiếu, in danh sách Điều thiếu để sửa regex.
- [ ] **Step 2:** Chạy → FAIL → hiện thực → PASS. Với bản 2012 kiểm tương tự số Điều cuối = 242.
- [ ] **Điểm commit:** `feat: article-based chunking`.

### Task 5: Embedder Ollama

**Files:**
- Modify: `starter/src/embeddings.py`
- Create: `starter/tests/test_embeddings.py`

**Interfaces:**
- Produces: `class EmbeddingBackendError(RuntimeError)`; `class OllamaEmbedder` với `__init__(self, model_name: str = EMBED_MODEL, base_url: str = OLLAMA_URL, batch_size: int = 16)`, thuộc tính `model_name`, `dimensions` (đo bằng một lần embed thử khi khởi tạo; khác `EMBED_DIM` → raise), `embed_documents(texts: list[str]) -> list[list[float]]`, `embed_query(question: str) -> list[float]`, `info() -> dict` (model, dimensions, ollama_version từ `/api/version`, digest từ `/api/tags`). Dùng `urllib.request`, timeout 120 s.

- [ ] **Step 1: Write tests**
  - `test_unreachable_backend_raises`: `OllamaEmbedder(base_url="http://127.0.0.1:9")` → `pytest.raises(EmbeddingBackendError)`, message chứa `"ollama"` và `"bge-m3"`.
  - `test_missing_model_raises`: `OllamaEmbedder(model_name="no-such-model-xyz")` → `EmbeddingBackendError` (đánh dấu `@pytest.mark.ollama`).
  - `test_real_dimensions_and_similarity` (`@pytest.mark.ollama`): `dimensions == 1024`; cosine("thời giờ làm thêm", "làm thêm giờ") > cosine("thời giờ làm thêm", "trả lương bằng tiền đồng").
  - `test_batch_order_preserved` (`@pytest.mark.ollama`): embed 20 chuỗi khác nhau theo batch 16 = embed từng chuỗi một (sai số < 1e-4).
- [ ] **Step 2:** Đăng ký marker `ollama` trong `starter/pytest.ini`. Chạy `python -m pytest tests/test_embeddings.py -v` → FAIL → hiện thực → PASS.
- [ ] **Điểm commit:** `feat: Ollama bge-m3 embedder`.

### Task 6: PgVectorStore

**Files:**
- Modify: `starter/src/store.py`
- Create: `starter/tests/test_store.py`

**Interfaces:**
- Produces `PgVectorStore(database_url: str, dimensions: int, table: str = "chunks")`:
  - `create_schema() -> None` — bảng cột: `chunk_id TEXT PK, strategy TEXT, document_id TEXT, version TEXT, source TEXT, page_start INT, page_end INT, printed_page_start INT, chuong TEXT, dieu INT, dieu_title TEXT, text TEXT, char_count INT, content_hash TEXT, embedding vector(dimensions)`. Không tạo index ANN.
  - `existing_hashes(strategy: str, document_id: str) -> dict[str, str]` (chunk_id → hash).
  - `upsert(strategy: str, chunks: list[Chunk], vectors: list[list[float]]) -> dict` — kiểm tra độ dài & số chiều (sai → `ValueError`), `ON CONFLICT DO UPDATE`, xóa chunk_id cũ của mỗi (strategy, document_id) có mặt trong `chunks` nhưng không còn trong lần này; trả `{"upserted": n, "deleted": m}`.
  - `copy_strategy(src: str, dst: str) -> int` — xóa toàn bộ dòng `dst` rồi chép dòng `src`, đổi `strategy` và tiền tố `chunk_id` `src:`→`dst:`.
  - `count(strategy: str | None = None) -> int`.
  - `search(strategy: str, query_vector: list[float], top_k: int = TOP_K, filters: dict | None = None) -> list[dict]` — chỉ cho phép khóa filter `version` (khóa khác → `ValueError`), tham số hóa SQL, `ORDER BY embedding <=> %s`, trả dict có `chunk_id, text, score (=1-distance), metadata{...}`.

- [ ] **Step 1: Write tests** (dùng DB Docker thật, `table="chunks_test"`, drop sau mỗi test, vector 1024 chiều tổng hợp):
  - `test_upsert_idempotent`: upsert cùng 5 chunk 2 lần → `count("A") == 5`.
  - `test_obsolete_chunks_deleted`: upsert 5 chunk rồi upsert 3 chunk (cùng document) → `count == 3`, result `deleted == 2`.
  - `test_dimension_mismatch_raises`: vector 3 chiều → `ValueError`.
  - `test_filter_restricts_version`: 2 chunk version `"2012"`, 2 chunk `"2019"`; `search(..., filters={"version": "2019"})` → mọi kết quả `metadata["version"] == "2019"`; `filters={"chuong": "x"}` → `ValueError`.
  - `test_copy_strategy`: copy `B`→`C` → `count("C") == count("B")`, chunk_id bắt đầu `"C:"`; copy lần 2 không nhân đôi.
  - `test_search_order_and_score`: vector truy vấn trùng chunk X → X ở top-1, `score` ≈ 1.0.
- [ ] **Step 2:** Chạy → FAIL → hiện thực → PASS.
- [ ] **Điểm commit:** `feat: pgvector store with idempotent upsert and version filter`.

### Task 7: Lệnh `ingest` và thống kê

**Files:**
- Modify: `starter/src/run.py`
- Create: `starter/tests/test_run_ingest.py`

**Interfaces:**
- Consumes: Task 2–6.
- Produces CLI `python -m src.run <command>` với `manifest`, `ingest`, `check-benchmark`, `evaluate --split {dev,test}`, `audit-templates`. `ingest`: load 2 PDF → chunk A và B → embed (bỏ qua chunk có `content_hash` không đổi) → upsert → `copy_strategy("B","C")` → ghi `results/ingest_stats.json` (theo strategy: `chunk_count`, `len_min/mean/p50/p95/max`, `total_chars`, `ingest_seconds`, `embedded_count`, `cost_usd: 0`, `reingest_check`) và `results/run_info.json` (model, digest, dims, ollama_version, pgvector version, thư viện PDF + version, timestamp, python version). Lỗi ghi `results/errors.log`.

- [ ] **Step 1: Write test** `test_ingest_twice_no_duplicates` (marker `ollama`, chỉ chạy với 3 trang đầu mỗi PDF qua tham số `--max-pages 3`): chạy ingest 2 lần → số dòng mỗi strategy bằng nhau giữa 2 lần, lần 2 `embedded_count == 0`.
- [ ] **Step 2:** Chạy → FAIL → hiện thực → PASS.
- [ ] **Step 3:** Chạy thật: `python -m src.run manifest; python -m src.run ingest; python -m src.run ingest` → `ingest_stats.json` có `reingest_check.same_counts == true`; ghi số chunk A/B/C.
- [ ] **Điểm commit:** `feat: ingest command with stats and reingest check`.

### Task 8: Benchmark — nháp, kiểm chứng, **người dùng chốt**

**Files:**
- Create: `starter/src/benchmark.py`, `starter/tests/test_benchmark.py`, `benchmark/questions.jsonl`, `benchmark/README.md`

**Interfaces:**
- Produces: `load_questions(path: Path) -> list[dict]`; `validate_questions(questions: list[dict], pages_by_doc: dict[str, list[DocumentPage]]) -> list[str]` (danh sách lỗi, rỗng = hợp lệ). Kiểm: đủ trường spec §6.7; `split ∈ {dev,test}`; ≥15 dev, ≥5 test; ≥3 câu có filter, ≥1 test có filter; `filter` là `null` hoặc `{"version": "2012"|"2019"}`; câu có filter phải chứa `"2012"` hoặc `"2019"` trong chính `question`; mỗi `evidence_quote` (gold và `alt_gold`) ≥ 30 ký tự sau bỏ khoảng trắng và có mặt trong trang gold (so khớp bằng `squash` — Task 8 tạo `squash` trong `src/evaluation.py` theo đúng định nghĩa ở Task 9, kèm test `test_squash_tolerates_split_syllables`; `benchmark.py` import từ đó).

- [ ] **Step 1: Write tests**
  - `test_rejects_unknown_filter_value`: filter `{"version": "2020"}` → có lỗi chứa `"version"`.
  - `test_rejects_filter_not_in_question`: filter 2019 nhưng câu hỏi không chứa "2019" → lỗi.
  - `test_rejects_short_or_missing_evidence`: evidence 10 ký tự → lỗi; evidence không có trên trang gold → lỗi.
  - `test_split_counts`: 14 dev → lỗi.
- [ ] **Step 2:** Chạy → FAIL → hiện thực → PASS.
- [ ] **Step 3 (Claude):** Soạn nháp 20 câu tiếng Việt vào `benchmark/questions.jsonl` theo spec §6.7: trộn loại trực tiếp / diễn đạt lại / điều kiện-ngoại lệ / phân biệt phiên bản; ≥3 câu filter (≥1 test); câu không filter phải có đáp án giống nhau ở 2 bộ luật (ghi cả hai vào gold + `alt_gold`) hoặc chỉ có ở một bộ luật. Đề xuất test = 5 câu từ các Chương khác với phần lớn dev.
- [ ] **Step 4:** `python -m src.run check-benchmark` → `0 problems`.
- [ ] **Step 5 — ĐIỂM CHẶN NGƯỜI DÙNG:** Người dùng tự mở PDF kiểm từng evidence, viết lại/thay ít nhất vài câu bằng diễn đạt của mình, chốt `split`. Chạy lại `check-benchmark` → `0 problems`. Ghi vào `benchmark/README.md`: cách chia, nguy cơ rò rỉ, "Câu hỏi do AI soạn nháp, tác giả duyệt và chỉnh sửa", **tiêu chí chọn chiến lược** (spec §6.8) và thời điểm chốt. Từ đây không sửa `split`.
- [ ] **Điểm commit:** `feat: benchmark questions frozen before experiments`.

### Task 9: Chấm truy xuất, trace và chỉ số

**Files:**
- Modify: `starter/src/evaluation.py`, `starter/src/run.py` (lệnh `evaluate`)
- Create: `starter/tests/test_evaluation.py`

**Interfaces:**
- Produces:
  - `squash(text: str) -> str` — NFC, lowercase, xóa mọi khoảng trắng.
  - `evaluate_query(question: dict, hits: list[dict]) -> dict` — trả `{"question_id", "split", "hit_positions": list[bool], "hit_at_1": bool, "hit_at_3": bool, "errors": list[str]}`; hit = cùng source_id, `[page_start, page_end]` giao `gold_page`, `squash(evidence) in squash(text)` — với gold chính hoặc bất kỳ `alt_gold`. Nếu không hit nhưng có ≥2 chunk top-3 cùng gold source/trang mà mỗi chunk chứa một phần evidence (≥ 30% đầu hoặc cuối) → `errors` có `"evidence_split"`.
  - `summarize(traces: list[dict]) -> list[dict]` — mỗi dòng `{strategy, split, n, hit1, hit3}`.
  - Lệnh `evaluate --split S`: với A, B, C chạy mọi câu của split; **chỉ C** truyền `filters=question["filter"]`, A/B luôn `None`; ghi `results/traces/{strategy}_{split}.jsonl` (question, filter_applied, top-3 với chunk_id, text, score, metadata, hit từng vị trí, errors) và cập nhật `results/metrics.csv`.

- [ ] **Step 1: Write tests**
  - `test_squash_tolerates_split_syllables`: `squash("ng ười s ử dụng lao động") == squash("người sử dụng lao động")`.
  - `test_hit_requires_page_and_evidence`: đúng evidence sai trang → không hit; đúng trang thiếu evidence → không hit.
  - `test_alt_gold_counts`: evidence chỉ khớp `alt_gold` (bộ luật kia) → hit.
  - `test_hit_at_1_vs_3`: hit chỉ ở vị trí 2 → `hit_at_1 False`, `hit_at_3 True`.
  - `test_summarize_counts`: 3 trace (2 hit3, 1 hit1) → `hit3 == 2`, `hit1 == 1`, `n == 3`.
  - `test_filter_only_for_C` (store giả lập ghi lại tham số `filters`): A/B nhận `None`, C nhận filter của câu; câu không filter → C nhận `None`.
- [ ] **Step 2:** Chạy → FAIL → hiện thực → PASS.
- [ ] **Step 3:** `python -m src.run evaluate --split dev` → `results/metrics.csv` có 3 dòng dev dạng n/N.
- [ ] **Step 4:** Áp tiêu chí chọn (spec §6.8, đã chốt ở Task 8) trên dev → ghi chiến lược được chọn + lý do vào `artifacts/experiment_log.csv` (điền đủ cột `strategy, chunking, chunk_size, overlap, metadata, filter, vectorizer, hypothesis, dev_hit1, dev_hit3, notes`) **trước** khi chạy test.
- [ ] **Step 5:** `python -m src.run evaluate --split test` → điền `test_hit1`, `test_hit3`.
- [ ] **Điểm commit:** `feat: retrieval evaluation, traces and metrics`.

### Task 10: Mẫu audit — **người dùng chấm**

**Files:**
- Create: `starter/src/audit.py`, `starter/tests/test_audit.py`; output `results/audit/coherence.csv`, `results/audit/metadata.csv`, `results/audit/grounding.csv`, `results/audit/README.md`

**Interfaces:**
- Produces: `coherence_rows(store, strategies=("A","B","C")) -> list[dict]` — với mỗi tài liệu × `COHERENCE_PAGES` lấy vị trí = ký tự đầu nội dung trang đó, tìm chunk của strategy chứa vị trí; cột `position_id, document_id, pdf_page, strategy, chunk_id, chunk_text, score_0_2, reason` (2 cột cuối **để trống**; dòng C ghi `reason` = "trùng chunk B — C dùng chung chunk với B" nhưng `score_0_2` vẫn trống). `metadata_rows(test_traces)` — 5 câu test × top-3 × strategy, cột `question_id, strategy, rank, chunk_id, source, page_start, page_end, version, dieu, filter, source_ok, page_ok, version_ok, dieu_ok, filter_ok, note` (các cột `_ok` và `note` trống). `grounding_rows(test_traces)` — 5 câu × strategy, cột `question_id, strategy, top3_chunk_ids, top3_text, expected_answer, score_0_2, reason` (2 cột cuối trống).

- [ ] **Step 1: Write tests**
  - `test_templates_have_empty_label_columns`: mọi dòng `score_0_2 == ""`; cột `_ok` trống.
  - `test_coherence_positions_fixed`: 10 position_id × 3 strategy = 30 dòng; `pdf_page ∈ {5,15,25,35,45}`.
- [ ] **Step 2:** Chạy → FAIL → hiện thực → PASS. `python -m src.run audit-templates` → 3 CSV.
- [ ] **Step 3 — ĐIỂM CHẶN NGƯỜI DÙNG:** Người dùng tự chấm cả 3 CSV đối chiếu PDF (ghi rõ người chấm là tác giả, nguy cơ thiên lệch trong `results/audit/README.md`).
- [ ] **Step 4:** Lệnh nhỏ `python -m src.run audit-summary` tính trung bình coherence /2, số bản ghi metadata đủ & đúng / tổng, filter tuân thủ n/N (hoặc N/A), grounding đếm 0/1/2 và trung bình /2 → `results/audit/summary.csv`. Test `test_audit_summary_counts` với CSV đã điền giả lập.
- [ ] **Điểm commit:** `feat: manual audit templates and summary`.

### Task 11: Báo cáo, README, nộp bài

**Files:**
- Create: `report/individual/2A202604002_BuiThaiSy.md` (copy từ `MSSV_HoTen.md`)
- Modify: `STUDENT.md`, `README.md` (thêm mục "Cách chạy bài làm"), `artifacts/experiment_log.csv`

- [ ] **Step 1:** Điền `STUDENT.md`: Bùi Thái Sỹ, 2A202604002, chủ đề "Bộ luật Lao động 2012 & 2019 (Công báo)". Lớp, repo, commit chốt: người dùng tự điền.
- [ ] **Step 2:** Thêm vào `README.md` mục lệnh tái lập: venv, `docker compose … up -d --wait`, `ollama pull bge-m3`, `python -m src.run manifest|ingest|check-benchmark|evaluate --split dev|evaluate --split test|audit-templates|audit-summary`, `python -m pytest -m "not ollama"` và `python -m pytest`.
- [ ] **Step 3 (Claude):** Nháp báo cáo từ **số liệu thật** trong `results/` theo mẫu: dữ liệu & quyền (Điều 15 Luật SHTT), chuẩn hóa & lỗi (con số từ `errors.log`), model/store/metric/chi phí 0, metadata + một trường hữu ích + một hạn chế, A/B/C, benchmark & tiêu chí chọn, 2 bảng kết quả, so sánh A–B và B–C, 2 ví dụ sai có ID câu và nguồn, giới hạn (test 5 câu, một người chấm, nguyên văn 2019 chưa sửa đổi, AI soạn nháp câu hỏi), công cụ AI đã dùng và cách kiểm tra.
- [ ] **Step 4 — NGƯỜI DÙNG:** sửa phần nhận xét/kết luận.
- [ ] **Step 5:** Đi qua checklist `SUBMISSION.md`; `git status` xác nhận không có `.env`, `.venv`. `python -m pytest` → toàn bộ PASS.
- [ ] **Điểm commit (cuối):** người dùng commit, push repo cá nhân, điền commit chốt vào `STUDENT.md`.
