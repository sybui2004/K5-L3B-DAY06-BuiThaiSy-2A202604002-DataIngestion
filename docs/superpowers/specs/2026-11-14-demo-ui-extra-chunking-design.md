# Giao diện demo truy xuất và các chiến lược chunking mở rộng — thiết kế

Ngày: 2026-11-14 · Nhánh: lab/day06-implementation · Trạng thái: chờ duyệt

## 1. Ý định và lý do

Bài lab Day 06 đã có pipeline (đọc PDF, chunking A/B/C, embedding bge-m3, pgvector) và benchmark đã chốt. Người học cần **trình bày trong buổi nộp bài** bằng một giao diện chạy được truy vấn thật, thay vì chỉ đưa bảng số. Giao diện phải giúp người xem *thấy* vì sao chiến lược này tốt hơn chiến lược kia, và người học muốn thử thêm các chiến lược chunking trong bảng so sánh (recursive, semantic, parent-child) để làm phần khám phá.

Người dùng: chính người học, trình bày trước giảng viên/hội đồng, màn hình chiếu. Thành công = demo trơn tru, mọi thao tác chạy trên dữ liệu thật, và giải thích được kết quả mà không phải mở terminal.

## 2. Mục tiêu / Không mục tiêu / Phản mục tiêu

Mục tiêu
- Chọn chiến lược, gõ câu hỏi, xem top-3 (điểm cosine, trang, Điều, metadata) trong một giao diện.
- Ba chiến lược mới D (recursive), E (semantic), F (parent-child) dùng được cùng A/B/C.
- Sáu phần trực quan, người học đã chọn cả sáu: so sánh song song; tô sáng chunk trên trang PDF; chạy benchmark một nút; bản đồ chunk; hiệu ứng bộ lọc năm; xem dữ liệu trong DB.
- Có thể xem DB bằng DBeaver (không cần code thêm, chỉ ghi hướng dẫn kết nối).

Không mục tiêu
- Không phải chatbot, không sinh câu trả lời bằng LLM.
- Không phải sản phẩm triển khai; chạy local trên máy người học.
- Không thay đổi bộ benchmark, split dev/test hay cơ chế freeze.
- Không có đăng nhập, nhiều người dùng, hay sửa/xóa dữ liệu từ giao diện.

Phản mục tiêu (thất bại dù kỹ thuật chạy được)
- Làm đổi hoặc ghi đè kết quả nộp bài của A/B/C (`results/metrics.csv`, `results/traces/`, `results/audit/`), hoặc làm đổi `chunk_id`/số dòng/vector khi chuyển A/B/C sang bảng riêng.
- Chạy tập test với chiến lược khám phá D/E/F rồi chọn dựa trên đó (phá nguyên tắc test chạy một lần).
- Demo hỏng giữa buổi vì phụ thuộc thứ chưa chạy (Ollama/Docker tắt mà không có thông báo rõ).

## 3. Ràng buộc

- Giữ stack hiện có: Python, PostgreSQL 16 + pgvector (Docker, cổng 127.0.0.1:55433), Ollama bge-m3 (1024 chiều), PyMuPDF. Thêm duy nhất `streamlit` (và thư viện biểu đồ đi kèm nếu cần) vào `starter/requirements.txt`.
- Embedding vẫn là bge-m3 cho mọi chiến lược (đảm bảo so sánh công bằng).
- pgvector không có khái niệm "folder": mỗi chiến lược là **một bảng riêng** `chunks_a` … `chunks_f` (quyết định ngày 2026-11-14, thay cho một bảng `chunks` có cột `strategy`). Bảng cũ `chunks` được giữ làm bản sao lưu cho tới khi người học cho xóa.
- Quy tắc git của người dùng: không tự commit; tài liệu này không được commit trừ khi người dùng yêu cầu.
- Benchmark đã freeze: `evaluate` hiện từ chối chạy nếu `questions.jsonl` đổi. Không được làm yếu kiểm tra này.
- Máy người học là Windows; mọi lệnh phải chạy được trên PowerShell/Git Bash.

## 4. Các hướng đã cân nhắc

| Hướng | Ưu | Nhược |
|---|---|---|
| **Streamlit (đã chọn)** | Toàn Python, gọi trực tiếp `PgVectorStore`/`OllamaEmbedder`/`run_strategy`; có sẵn cột, tab, bảng, biểu đồ, hiển thị ảnh; một lệnh chạy | Giao diện kém tự do; chạy lại script mỗi lần bấm (giảm bằng cache) |
| FastAPI + HTML/JS | Đẹp, sát mockup nhất | Gấp 2–3 lần khối lượng, nhiều chỗ lỗi trước demo |
| Gradio | Nhanh | Khó làm bố cục ba cột có tô sáng và dashboard |

Người học đã chọn Streamlit.

## 5. Quyết định đã chốt với người học

- Bố cục A, một trang ba cột: trái = chiến lược + bộ lọc năm + chọn so sánh song song; giữa = ô câu hỏi (kèm menu câu mẫu từ benchmark) + nút truy xuất + top-3; phải = giải thích (trang PDF tô sáng, điểm cosine, metadata).
- Giữ A/B/C làm bài nộp; D/E/F là phần khám phá trên giao diện.
- Benchmark trong giao diện chỉ chạy trên dev và ghi vào file riêng; tập test chỉ hiển thị số liệu A/B/C đã chạy chính thức.
- DB chỉ đọc trong giao diện; thêm chunk chiến lược mới qua lệnh ingest.
- Sáu phần trực quan: giữ đủ cả sáu.

## 6. Thiết kế

### 6.0 Lưu trữ: mỗi chiến lược một bảng

- Bảng `chunks_a`, `chunks_b`, `chunks_c`, `chunks_d`, `chunks_e`, `chunks_f`, cùng cột như bảng `chunks` hiện tại (giữ cả cột `strategy` để dòng dữ liệu giữ nguyên hình dạng); riêng `chunks_f` có thêm `parent_id`, `parent_text`. Không có index ANN (exact search như cũ). Lợi ích chính: cấu trúc cột riêng từng chiến lược, nạp lại/xóa độc lập, dễ duyệt trong DBeaver; tốc độ truy xuất gần như không đổi ở quy mô ~500 chunk/chiến lược.
- `PgVectorStore` ánh xạ `strategy -> tên bảng` (`{prefix}_{strategy.lower()}`, prefix mặc định `chunks`); chữ ký các phương thức giữ nguyên để code hiện có (`run.py`, `evaluation.py`, `audit.py`) không phải đổi.
- Di chuyển dữ liệu: lệnh `python -m src.run migrate-tables` chép các dòng A/B/C từ bảng cũ `chunks` sang bảng mới bằng `INSERT ... SELECT ... ON CONFLICT DO NOTHING` (không embed lại, giữ nguyên `chunk_id` và vector). Bảng cũ không bị sửa hay xóa. Xác minh: số dòng khớp 501/505/505 và top-3 của vài câu truy vấn trùng với trước khi chuyển.

### 6.1 Chiến lược mới (mỗi chiến lược một bảng)

| Mã | Tên | Cách làm |
|---|---|---|
| D | Recursive | Tách theo thứ bậc: đoạn trống → dòng → câu → ký tự, gom tới kích thước đích (gợi ý 800 ký tự, chồng lấn 100, như A để so sánh công bằng) |
| E | Semantic | Tách thành câu, embed từng câu bằng bge-m3, cắt chỗ độ tương đồng giữa hai câu liền kề giảm dưới ngưỡng, kèm giới hạn kích thước tối đa |
| F | Parent-child | Chunk con nhỏ được embed và tìm kiếm; kết quả trả về kèm văn bản cha (cả Điều). Bảng `chunks_f` có thêm cột `parent_text` và `parent_id`; các bảng khác không có |

Mọi chunk D/E/F dùng cùng metadata như A/B (document_id, version, trang đầu/cuối, chương, Điều, hash) và cùng cơ chế upsert theo `content_hash` để nạp lại không tạo dòng trùng. Lệnh mới: `python -m src.run ingest --strategy D|E|F`, không đụng tới các dòng A/B/C. Với F, giao diện hiển thị văn bản cha nhưng điểm/Hit tính trên chunk con trúng.

### 6.2 Giao diện (`streamlit run`, file mới trong `starter/`)

- Khởi động: kiểm tra Postgres và Ollama; nếu thiếu, hiện thông báo rõ cách khởi động thay vì lỗi trần.
- Cột trái: danh sách chiến lược với số chunk (đọc từ DB), chip trạng thái "đã nạp / chưa nạp" cho D/E/F; bộ lọc năm (Tất cả / 2019 / 2012); chọn các chiến lược để so sánh song song.
- Cột giữa: ô câu hỏi, menu 20 câu mẫu từ benchmark, nút "Truy xuất top-3". Mỗi kết quả hiện hạng, Điều, trang, điểm, đoạn văn, và dấu ✅ nếu câu mẫu có gold và chunk chứa evidence. Chế độ so sánh hiện nhiều cột cạnh nhau.
- Cột phải: trang PDF gold/trang của kết quả được chọn, vẽ bằng PyMuPDF, vùng chunk tô màu (chunk nhiều trang: tô trang đầu, ghi chú các trang còn lại); biểu đồ điểm cosine top-3; bảng metadata.
- Tab "Benchmark": nút chạy dev cho các chiến lược đã nạp, bảng Hit@1/Hit@3, nhấp một câu sai để xem top-3. Kết quả lưu `results/explore/` (không phải `results/metrics.csv`). Số liệu test A/B/C chỉ đọc từ `results/metrics.csv` đã có.
- Tab "Bản đồ chunk": dải màu theo trang, mỗi ô một chunk, kèm biểu đồ phân bố độ dài, cho từng chiến lược.
- Tab "Bộ lọc năm": cho một câu hỏi, so kết quả có/không filter (B vs C).
- Tab "Dữ liệu DB": chỉ đọc; số chunk mỗi chiến lược, 20 dòng mẫu, câu SQL tương đương và hướng dẫn kết nối DBeaver (host 127.0.0.1, cổng 55433, DB day6_lab, user day6; mật khẩu lấy từ `starter/.env`, không in ra giao diện).

### 6.3 Tái sử dụng, không viết lại

Giao diện gọi các hàm hiện có (`PgVectorStore.search`, `OllamaEmbedder.embed_query`, `evaluation.is_hit`/`run_strategy`, `load_corpus`). Phần dùng chung giữa giao diện và CLI (ví dụ danh sách chiến lược, hàm chunker) đặt ở một chỗ để không lặp.

### 6.4 Xử lý lỗi và an toàn

- Ollama/Postgres không chạy: thông báo có hướng dẫn, không mock vector.
- Chiến lược chưa nạp: nút bị vô hiệu kèm lệnh ingest cần chạy.
- Giao diện chỉ dùng truy vấn SELECT; mọi ghi dữ liệu chỉ qua lệnh ingest.
- Không chạy `evaluate --split test` cho D/E/F ở bất kỳ đâu.

### 6.5 Kiểm thử

- Test đơn vị cho chunker D/E/F (không mất văn bản, kích thước trong giới hạn, trang/Điều đúng, nạp lại idempotent), cho ánh xạ vùng tô sáng và cho cột parent_text của F, theo phong cách pytest hiện có (`starter/tests`).
- Kiểm thử thủ công trước demo: chạy một câu mẫu trên từng chiến lược, bật/tắt filter, chạy benchmark dev, đối chiếu số liệu A/B/C với `results/metrics.csv`.
- Hồi quy: toàn bộ 51 test hiện có vẫn qua; `python -m src.run evaluate` vẫn bị chặn nếu benchmark thay đổi.

## 7. Để người xây quyết định

- Tên file/thư mục cụ thể của ứng dụng và mô-đun dùng chung.
- Ngưỡng cắt cho semantic (E) và kích thước chunk con của F: chọn giá trị hợp lý, ghi vào `config.py`, nêu trong báo cáo.
- Cách ánh xạ chunk về vùng trên trang PDF (tìm văn bản bằng PyMuPDF hoặc tương đương), miễn tô đúng trang và vùng gần đúng.
- Biểu đồ dùng thư viện nào đi kèm Streamlit.

## 8. Các điểm do người soạn tự quyết (đề nghị kiểm tra)

1. Giữ cột `strategy` trong mọi bảng chiến lược; `parent_text`/`parent_id` chỉ có ở `chunks_f`.
2. D dùng cùng kích thước/chồng lấn như A (800/100) để chỉ khác ở cách tách.
3. Kết quả benchmark khám phá ghi vào `results/explore/`, tách khỏi kết quả nộp.
4. Chỉ tô trang đầu với chunk nhiều trang.
