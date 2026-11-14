# Thiết kế — Day 06 Data Ingestion Lab (Bộ luật Lao động 2012 & 2019)

Ngày: 2026-11-13 · Trạng thái: đã duyệt

## 1. Mục đích

Hoàn thành lab cá nhân Day 06 (4 giờ): biến hai văn bản luật tiếng Việt thành kho tri thức truy xuất được, so sánh **3 chiến lược dữ liệu** trên cùng corpus/model/benchmark và báo cáo đủ **5 khía cạnh** theo `GUIDE.md`, `BENCHMARK.md`, `RUBRIC.md`. Điểm chấm dựa trên bằng chứng và khả năng tái lập, không dựa vào Hit@3 cao.

## 2. Mục tiêu / Không làm / Thất bại dù chạy được

**Mục tiêu**
- Pipeline Python đọc PDF → chuẩn hóa → chunk → embed → lưu pgvector → truy xuất top-3, chạy lại được bằng một lệnh.
- 3 cấu hình A/B/C với hai phép so sánh có kiểm soát: A–B (chỉ đổi chunking), B–C (chỉ đổi filter).
- Benchmark ≥20 câu tiếng Việt có gold evidence, tách 15 dev / 5 test **trước** khi chạy.
- Trace đầy đủ, chỉ số dev/test, nhãn audit thủ công, báo cáo cá nhân.

**Không làm**
- Không xây chatbot / không sinh câu trả lời bằng LLM.
- Không làm hybrid BM25 (mở rộng tùy chọn, chỉ làm nếu dư thời gian).
- Không dùng LLM judge.

**Thất bại dù chạy được (anti-goals)**
- Fallback âm thầm sang vector giả khi Ollama/DB lỗi.
- Đưa gold source/đáp án vào query hoặc filter; tinh chỉnh theo test rồi báo như holdout.
- Số liệu, nhãn hoặc log không do chạy thật tạo ra.
- Nạp lại sinh bản ghi trùng.

## 3. Ràng buộc

- Windows 11, Python 3.11, Docker 28 (đã có), Ollama 0.40.16 (đã có, đang chạy).
- Không commit `.env`, venv, model weights. Không có dữ liệu cá nhân/mật.
- Mọi lỗi backend (Ollama, PostgreSQL) phải dừng chương trình với thông báo rõ.

## 4. Corpus

| document_id | Văn bản | version | Nguồn chính thức | Trang PDF | Trang Công báo in |
|---|---|---|---|---|---|
| `blld-2012` | Bộ luật Lao động số 10/2012/QH13 | `2012` | congbao.chinhphu.vn/van-ban/luat-so-10-2012-qh13-2771.htm (Công báo số 475+476, 05-8-2012) | 83 | 3–85 |
| `blld-2019` | Bộ luật Lao động số 45/2019/QH14 | `2019` | congbaocdn.chinhphu.vn/CongBaoCP/VanBan/2019/11/30232/29070-1-2019993-99445-2019-qh14.pdf (Công báo số 993+994, 26-12-2019) | 94 (trang 94 rỗng) | 3–… |

- **Giấy phép:** văn bản quy phạm pháp luật không thuộc phạm vi bảo hộ quyền tác giả (khoản 2 Điều 15 Luật Sở hữu trí tuệ). Không chứa dữ liệu cá nhân → được phép lưu trong repo và xử lý local.
- **Lưu file:** `data/raw/blld_2012_congbao.pdf`, `data/raw/blld_2019_congbao.pdf`. Hai file **đã tải và đo** (số trang, lỗi glyph ở 6.2 quan sát trên chính các file này) đang nằm ở scratchpad của phiên brainstorm; bước đầu của kế hoạch là chép chúng vào `data/raw/` và tính sha256. Link tải trực tiếp bản 2012: `https://g7.cdnchinhphu.vn/api/download/stream?Url=tm-8mq6BhNw0NbrKRhTDAQWsKg3tuqaY0aWypnY78U6M2BY68Ekp0Gvvr483flbR1AX-Ev7tC9j_xrnIJnKDk1P0Swr6bixBELf12brVHLVoBxxF5xGzGyzWINg0gwK6&file_name=2012_475+%2b+476-10_2012_QH13.pdf` (lấy từ nút tải trên trang Công báo).
- **Quy tắc đếm trang nội dung:** một trang PDF được tính nếu sau chuẩn hóa còn ≥ 200 ký tự nội dung luật (không tính dòng header Công báo). Dự kiến ~176 trang (83 + 93). Trang rỗng được ghi log, không tính.
- **Giới hạn đã biết:** Bộ luật 2019 đã được sửa đổi bởi các luật năm 2025 (có văn bản hợp nhất 2026). Corpus dùng **nguyên văn ban hành**; mọi đáp án benchmark theo nguyên văn này, không phải luật đang áp dụng; ghi rõ trong báo cáo. Ngày hiệu lực trong manifest **chỉ lấy từ điều khoản hiệu lực trong chính văn bản** (không lấy từ nguồn web — `RULES.md`/`GUIDE.md` cấm đoán ngày hiệu lực).
- **Manifest** `data/manifest.csv`: `source_id, title, source_url, license_or_permission, accessed_at (2026-11-13), physical_pages, counted_pages (danh sách), excluded_pages + lý do, char_count, sha256, gazette_issue`.

## 5. Các phương án đã cân nhắc

| # | A | B | C | Đánh giá |
|---|---|---|---|---|
| **① (chọn)** | Cố định 800 ký tự, overlap 100 | Theo Điều; Điều > 1.500 ký tự tách theo khoản, mỗi phần giữ header "Điều X. Tên" | B + filter `version` khi câu hỏi nêu năm | A–B và B–C mỗi cặp đổi đúng một yếu tố; filter theo năm là nhu cầu thật của corpus hai phiên bản |
| ② | như ① | Theo từng khoản | B + filter | Chunk ngắn có thể tăng Hit@1 nhưng khoản đứng riêng mất ngữ cảnh ("trường hợp tại khoản 1…"), coherence thấp, evidence điều kiện dễ bị tách |
| ③ | như ① | như ① | B + filter `chuong` | Người hỏi không biết chương; dễ rò rỉ gold vào filter. Loại |

Chọn ① (Claude đề xuất, người dùng nhờ Claude chọn).

## 6. Thiết kế đã chốt

### 6.1 Công nghệ
- **Embedding:** `bge-m3` qua Ollama (`ollama pull bge-m3`), 1024 chiều, gọi `POST http://localhost:11434/api/embed`. Query và document xử lý giống nhau, không tiền tố. Ghi digest model (`ollama list`) và version Ollama vào `results/run_info.json`.
- **Vector store:** PostgreSQL 16 + pgvector 0.8 qua `starter/docker-compose.yml`. Metric cosine (`<=>`), **exact search** (không tạo index ANN — ~3k vector, tránh filter làm hụt kết quả).
- **Đọc PDF:** pypdf (đã có trong `starter/requirements.txt`); builder được thử PyMuPDF nếu cho ít lỗi tách chữ hơn (xem 6.2), ghi lý do chọn.

### 6.2 Chuẩn hóa (ghi log từng loại lỗi + số lần)
Lỗi đã quan sát khi trích xuất thử:
1. Header mỗi trang `CÔNG BÁO/Số … /Ngày …` kèm số trang in → bỏ dòng header, lưu số trang in vào `printed_page`.
2. Bản 2019: khoảng trắng chèn giữa âm tiết (`thỏa thu ận`, `ng ười s ử dụng`). Không có quy tắc sửa an toàn tuyệt đối → giữ văn bản, **đo tỷ lệ** và ghi vào log; xử lý ảnh hưởng ở khâu so khớp evidence (6.6).
3. Bản 2012: lỗi glyph dấu gạch thành `ộ`/`Ị` (`05ộ8ộ2012`, `Độc lập Ị Tự do`). Chỉ thay khi ngữ cảnh chắc chắn (giữa hai chữ số; `Ị` đứng riêng giữa hai khoảng trắng). `ộ`, `Ị` là chữ tiếng Việt hợp lệ nên không thay toàn cục.
4. Unicode NFC; gộp khoảng trắng thừa; giữ xuống dòng ở đầu `Chương`, `Mục`, `Điều`, khoản `1.`, điểm `a)`.

### 6.3 Chunking
Văn bản mỗi tài liệu được nối thành một dòng chảy liên tục kèm bảng offset → trang, để chunk vắt qua trang vẫn biết `page_start`/`page_end`.

- **A — fixed:** cửa sổ 800 ký tự, overlap 100, trên dòng chảy của từng tài liệu (không vắt qua hai tài liệu). Metadata `chuong`/`dieu` lấy theo vị trí đầu chunk.
- **B — theo Điều:** tách tại `Điều <số>.`; phần mở đầu và tiêu đề Chương/Mục không thành chunk riêng mà vào metadata. Điều > 1.500 ký tự: gom các khoản liên tiếp đến ≤ 1.500 ký tự, mỗi phần mở đầu bằng `Điều X. <tên điều>`; khoản đơn lẻ > 1.500 ký tự tách theo câu.
- **C:** **chép các dòng của B sang `strategy = 'C'`** (cùng text, metadata, vector — không gọi embed lại) để có đủ 3 index đúng câu chữ `CHECKPOINTS.md`; khác B duy nhất ở mệnh đề `WHERE version = %s` khi câu hỏi có `filter`. Câu không có filter → C chạy như B, ghi rõ trong trace. Báo cáo ghi C có cùng số chunk/coherence với B và lý do.

### 6.4 Metadata mỗi chunk
`chunk_id` (ổn định: `{strategy}:{document_id}:{index hoặc dieu-part}`), `strategy` (`A`|`B`|`C`), `document_id`, `source` (đường dẫn file), `version` (`2012`|`2019`, từ tên văn bản — trường filter), `page_start`, `page_end` (trang PDF 1-based), `printed_page_start` (trang Công báo), `chuong` (vd `Chương VII`), `dieu` (int), `dieu_title`, `char_count`, `content_hash` (sha256 text).

### 6.5 Lưu trữ & nạp lại
- Một bảng `chunks` với cột `embedding vector(1024)`, khóa chính `chunk_id`.
- Upsert `ON CONFLICT (chunk_id) DO UPDATE`; bỏ qua embed lại nếu `content_hash` không đổi.
- Khi nạp lại một tài liệu: xóa các `chunk_id` của (strategy, document_id) không còn trong lần nạp mới.
- Kiểm tra nạp lại: chạy ingest 2 lần, số dòng không đổi → ghi vào `results/ingest_stats.json`.

### 6.6 Truy xuất & chấm tự động
- Top-3 theo cosine, `score = 1 - distance`.
- **Hit** của một chunk = cùng `gold_source_id` **và** trang giao với `gold_pages` **và** chứa đủ `evidence_quote` (hoặc một evidence thay thế đã ghi). So khớp trên chuỗi đã NFC + lowercase + **xóa toàn bộ khoảng trắng** để không bị lỗi tách âm tiết đánh trượt; `evidence_quote` tối thiểu 30 ký tự (sau khi bỏ khoảng trắng) để tránh trùng nhầm; áp dụng giống nhau cho mọi strategy; ghi rõ quy tắc này trong báo cáo.
- Hit@1 = top-1 hit / N; Evidence Hit@3 = có ≥1 hit trong top-3 / N. Báo n/N, tách dev/test, theo từng strategy. Evidence bị tách qua nhiều chunk → ghi lỗi `evidence_split`.

### 6.7 Benchmark (`benchmark/questions.jsonl`)
- 20 câu tiếng Việt, tự viết từ corpus, **tách 15 dev / 5 test trước khi chạy**, ghi lý do tách trong `benchmark/README.md`.
- Trường bắt buộc đúng tên theo `BENCHMARK.md`: `id, split, question, expected_answer, gold_source_id, gold_page, evidence_quote, filter (null | {"version": "2012"|"2019"})`; thêm `type`, `gold_dieu` và `alt_gold` (list các {source_id, page, dieu, evidence_quote}, có thể rỗng) để ghi mọi nguồn hợp lệ khác (vd câu có đáp án ở cả hai bộ luật). Hit với gold chính hoặc bất kỳ phần tử `alt_gold` nào đều là hit.
- Loại câu: trực tiếp, diễn đạt lại, điều kiện/ngoại lệ, phân biệt phiên bản. ≥ 3 câu có filter, ≥ 1 trong test.
- **Quy tắc phiên bản:** câu có filter chỉ khi chính câu hỏi nêu năm/số hiệu. Câu **không** filter phải có đáp án giống nhau ở cả hai bộ luật (khi đó ghi gold cho cả hai) hoặc nội dung chỉ có ở một bộ luật — không dùng câu mơ hồ giữa hai phiên bản.
- Tách test theo chủ đề (Chương) khác với phần lớn dev khi khả thi; ghi nguy cơ rò rỉ.
- Kiểm chứng: script kiểm tra mọi `evidence_quote` tồn tại trong trang gold sau chuẩn hóa (cùng quy tắc so khớp 6.6) trước khi chạy thử.

### 6.8 Tiêu chí chọn chiến lược (chốt trước khi xem test)
Ưu tiên Evidence Hit@3 trên dev → Hit@1 trên dev → coherence trung bình → ít chunk/thời gian ingest hơn. Áp dụng xong mới chạy test.

### 6.9 Audit thủ công (người chấm: tác giả; ghi nguy cơ thiên lệch)
- **Coherence:** 10 vị trí cố định chọn trước khi xem điểm = ký tự đầu nội dung các trang PDF 5, 15, 25, 35, 45 của mỗi tài liệu; với A và B (C dùng chunk của B nên cùng điểm B), chấm chunk chứa vị trí 0/1/2 kèm lý do → `results/audit/coherence.csv`.
- **Metadata:** 5 câu test × top-3 × mỗi strategy, kiểm `source`, `page`, `version`, `dieu` so với PDF → số bản ghi đủ & đúng / tổng; tỷ lệ tuân thủ filter cho câu có filter (N/A nếu không có) → `results/audit/metadata.csv`. Báo cáo nêu ít nhất một trường hữu ích (`version` cho lọc) và một hạn chế (vd `dieu` của chunk A chỉ phản ánh vị trí đầu chunk).
- C có dòng riêng trong mọi bảng audit (coherence ghi "trùng B" kèm lý do).
- **Grounding:** 5 câu test × mỗi strategy, chấm top-3 0/1/2 kèm lý do → `results/audit/grounding.csv`. Không gọi là độ chính xác câu trả lời.

### 6.10 Đầu ra
- `results/traces/{strategy}.jsonl`: câu hỏi, filter áp dụng, top-3 (chunk_id, text, score, metadata), hit từng vị trí, nhãn lỗi.
- `results/metrics.csv` (strategy × split: Hit@1 n/N, Hit@3 n/N), `results/ingest_stats.json` (số chunk, phân bố độ dài, tổng ký tự, thời gian ingest, chi phí = 0, kiểm tra nạp lại), `results/errors.log`, `results/run_info.json`.
- `artifacts/experiment_log.csv` điền A/B/C; `report/individual/<MSSV>_<HoTen>.md`; `STUDENT.md`; README root bổ sung lệnh setup/run.

### 6.11 Vị trí code
Hoàn thiện các module có sẵn trong `starter/src/` (`ingestion.py`, `chunking.py`, `embeddings.py`, `store.py`, `evaluation.py`, `run.py`), chạy `python -m src.run` từ `starter/`. Đường dẫn data/benchmark/results tính từ root repo.

## 7. Phân công người – AI (người dùng đã chốt)
| Hạng mục | Claude | Người dùng (tác giả, người chấm) |
|---|---|---|
| 20 câu benchmark | Soạn nháp kèm evidence; script kiểm chứng evidence nằm đúng trang | **Bắt buộc:** tự mở PDF kiểm từng evidence, tự viết lại/thay ít nhất vài câu bằng diễn đạt của mình, rồi **chốt split dev/test trước mọi lần chạy** (điểm chặn) — vì `BENCHMARK.md`/`RULES.md` yêu cầu "tự xây", "tự xác minh" |
| Audit coherence / metadata / grounding | Sinh CSV mẫu có chunk, **cột điểm để trống** | Tự chấm 0/1/2 và ghi lý do (điểm chặn sau khi chạy) |
| Code, ingest, chạy, metrics | Làm | Chạy lại kiểm tra |
| Báo cáo cá nhân | Nháp từ số liệu thật | Sửa phần nhận xét, kết luận |

Báo cáo ghi rõ: "Câu hỏi do AI soạn nháp, tác giả duyệt; nhãn audit do tác giả chấm".

**Học viên:** Bùi Thái Sỹ — MSSV 2A202604002 → báo cáo `report/individual/2A202604002_BuiThaiSy.md`, điền `STUDENT.md`.

## 7b. Để builder quyết định
- Regex cụ thể nhận diện Chương/Mục/Điều/khoản và xử lý glyph lỗi.
- pypdf hay PyMuPDF (chọn bên ít lỗi hơn, ghi lý do).
- Batch size khi gọi Ollama, cấu trúc CLI (`--ingest`, `--evaluate`…), cách tổ chức hàm phụ.

## 8. Quyết định Claude tự đưa ra (để người dùng kiểm tra)
- Kích thước A 800/100, ngưỡng B 1.500 ký tự.
- C là bản chép các dòng của B (không embed lại) — người dùng đã đồng ý.
- Exact search, không index ANN.
- So khớp evidence bỏ toàn bộ khoảng trắng.
- 10 vị trí coherence theo trang PDF 5/15/25/35/45 mỗi tài liệu.
- Ngưỡng 200 ký tự cho "trang nội dung".
