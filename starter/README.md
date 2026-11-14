# Pipeline · PostgreSQL + pgvector + bge-m3

Pipeline ingestion và benchmark cho corpus **Bộ luật Lao động 2012 và 2019** (Công báo, 2 PDF trong `../data/raw/`). Các bước: đọc PDF bằng PyMuPDF, chuẩn hóa, chunk theo 3 cấu hình A/B/C, embed bằng `bge-m3` (Ollama, chạy local), lưu và truy xuất bằng PostgreSQL 16 + pgvector 0.8.7 (cosine, exact search), chấm Hit@1/Evidence Hit@3, rồi tạo template audit thủ công. Báo cáo nằm ở [`../report/individual/2A202604002_BuiThaiSy.md`](../report/individual/2A202604002_BuiThaiSy.md).

## Cấu trúc

```text
starter/
├── docker-compose.yml     # PostgreSQL 16 + pgvector 0.8.7, chỉ mở cổng 127.0.0.1:55433
├── init.sql               # bật extension vector khi tạo database mới
├── requirements.txt       # psycopg, pymupdf, python-dotenv, pytest, streamlit
├── .env.example           # copy thành .env (DATABASE_URL, OLLAMA_URL tùy chọn)
├── app.py                 # giao diện demo Streamlit (tùy chọn)
├── scripts/
│   ├── check_setup.py     # kiểm tra kết nối database và extension
│   └── draft_benchmark.py # hỗ trợ soạn nháp câu hỏi (tác giả duyệt lại thủ công)
├── src/
│   ├── config.py          # đường dẫn, model, tham số chunk (A_SIZE, B_MAX, ...)
│   ├── ingestion.py       # đọc PDF, bỏ header Công báo, chuẩn hóa NFC, cờ trang nội dung
│   ├── manifest.py        # ghi ../data/manifest.csv
│   ├── chunking.py        # A: fixed-size 800/100; B: theo Điều, tối đa 1.500 ký tự
│   ├── embeddings.py      # OllamaEmbedder (bge-m3, 1024 chiều), không fallback sang mock
│   ├── store.py           # PgVectorStore: bảng chunks_a/b/c, upsert theo content_hash, filter version
│   ├── benchmark.py       # kiểm tra questions.jsonl, đóng băng bằng sha256
│   ├── evaluation.py      # Hit@1 / Evidence Hit@3, trace top-3
│   ├── audit.py           # template coherence/metadata/grounding và tổng hợp
│   ├── run.py             # CLI
│   └── chunking_extra.py, ingest_extra.py, strategies.py, explore/   # chiến lược khám phá D/E/F + demo
└── tests/                 # pytest
```

Kết quả nằm ở thư mục gốc repo: `../results/` (trace, metrics, audit, log), `../benchmark/`, `../data/manifest.csv`, `../artifacts/experiment_log.csv`.

## 1. Cài đặt

Cần Docker Desktop (hoặc Docker Engine + Compose), Python 3.11 và [Ollama](https://ollama.com). Bản đã chạy: Python 3.11.0, Ollama 0.40.16, `bge-m3` digest `7907646426…`, PyMuPDF 2.1. Mọi lệnh chạy từ thư mục `starter/`:

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1   |   macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
# Windows: Copy-Item .env.example .env   |   macOS/Linux: cp .env.example .env
docker compose -p day6_student_starter up -d --wait
python scripts/check_setup.py            # kỳ vọng: "Setup OK"
ollama pull bge-m3                       # model embedding local, không cần API key, chi phí 0
```

`.env` chỉ cần `DATABASE_URL` (đã có sẵn trong `.env.example`). Không cần key API. Mật khẩu database là giá trị cố định chỉ dùng local cho lab. Nếu cổng 55433 bận, sửa đồng thời `docker-compose.yml` và `DATABASE_URL`. Nếu Ollama không chạy hoặc thiếu model, pipeline dừng với `EmbeddingBackendError` thay vì dùng vector giả.

Dừng container nhưng giữ dữ liệu: `docker compose -p day6_student_starter stop`.

## 2. Chạy lại toàn bộ pipeline A/B/C

```bash
python -m src.run manifest                 # ghi ../data/manifest.csv (trang, ký tự, sha256)
python -m src.run ingest                   # A và B: chunk + embed + upsert; C = bản sao B  (≈ 3 phút lần đầu)
python -m src.run ingest                   # chạy lại: 0 chunk embed lại, số chunk không đổi (same_counts: true)
python -m src.run check-benchmark          # kỳ vọng: "0 problems"
python -m src.run evaluate --split dev     # ../results/traces/{A,B,C}_dev.jsonl + ../results/metrics.csv
python -m src.run evaluate --split test    # chỉ chạy sau khi đã chốt chiến lược trên dev
python -m src.run audit-templates          # tạo ../results/audit/{coherence,metadata,grounding}.csv (không ghi đè file đã có)
python -m src.run audit-summary            # ../results/audit/summary.csv từ các nhãn đã chấm tay
python -m pytest -q                        # 127 test
```

- **Cấu hình:** A = fixed-size 800 ký tự, overlap 100. B = theo Điều, tối đa 1.500 ký tự (Điều dài được tách theo khoản, mỗi phần lặp lại tiêu đề Điều). C = cùng chunk và vector với B, chỉ thêm `WHERE version = <năm>` khi câu hỏi tự nêu năm của bộ luật.
- **Nạp lại và tài liệu đổi:** `chunk_id` ổn định, mỗi chunk có `content_hash`. Chunk nào hash không đổi thì không embed lại; chunk nào đổi thì upsert (`ON CONFLICT (chunk_id) DO UPDATE`); chunk không còn trong tài liệu thì bị xóa (`delete_obsolete`). Kết quả mỗi lần ingest được ghi thêm vào `../results/ingest_history.jsonl`. Lưu ý: `ingest_stats.json` chỉ giữ lần chạy gần nhất. Thời gian ingest có embed của lần đầu nằm ở dòng 1 của `ingest_history.jsonl`.
- **Benchmark đóng băng:** `evaluate` từ chối chạy nếu sha256 của `../benchmark/questions.jsonl` khác `../benchmark/frozen.json`.
- **Bảng cũ:** các lần chạy trước có thể còn một bảng `chunks` duy nhất (có cột `strategy`). `python -m src.run migrate-tables` chép bảng đó sang `chunks_a/b/c` mà không embed lại. Cài mới từ đầu thì không cần lệnh này.

Không commit `.env`, `.venv` hoặc dữ liệu không được phép chia sẻ (đã có trong `.gitignore`).

## 3. Giao diện demo và chiến lược khám phá (D/E/F)

**Mỗi chiến lược là một bảng riêng** trong PostgreSQL: `chunks_a`, `chunks_b`, `chunks_c` (bài nộp, đã đóng băng benchmark) và `chunks_d`, `chunks_e`, `chunks_f` (khám phá). pgvector không có "folder": vector là một cột `embedding vector(1024)` trong bảng thường. Riêng `chunks_f` có thêm `parent_id`, `parent_text`. Bảng cũ `chunks` (một bảng có cột `strategy`) được giữ làm bản sao lưu; chuyển dữ liệu A/B/C sang bảng mới bằng `python -m src.run migrate-tables` (không embed lại, chạy lại nhiều lần vẫn an toàn).

```bash
# từ thư mục starter/, đã kích hoạt .venv, Docker + Ollama đang chạy
python -m src.run ingest --strategy D      # recursive   (≈ 90 giây)
python -m src.run ingest --strategy F      # parent-child
python -m src.run ingest --strategy E      # semantic    (embed từng câu, lâu hơn)
streamlit run app.py                       # giao diện demo
```

Kết quả của D/E/F và benchmark chạy trên giao diện (chỉ tập dev) nằm trong `results/explore/`; không ảnh hưởng `results/metrics.csv`, `results/traces/` hay `results/audit/` dùng để nộp. Tập test không chạy cho D/E/F.

**Xem dữ liệu bằng DBeaver:** New Database Connection → PostgreSQL → Host `127.0.0.1`, Port `55433`, Database `day6_lab`, Username `day6`, Password lấy từ `DATABASE_URL` trong `starter/.env`. Các bảng `chunks_*` nằm ở schema `public`. Ví dụ: `SELECT chunk_id, page_start, dieu, left(text, 80) FROM chunks_b ORDER BY chunk_id LIMIT 20;`
