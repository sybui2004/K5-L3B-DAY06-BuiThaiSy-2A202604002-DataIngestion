# Benchmark — Bộ luật Lao động 2012 & 2019

File: `questions.jsonl` (20 câu: 15 dev / 5 test). Kiểm chứng: `cd starter && python -m src.run check-benchmark` → phải in `0 problems`.

## Trường dữ liệu

`id, split, type, question, expected_answer, gold_source_id, gold_page, gold_dieu, evidence_quote, alt_gold, filter`

- `gold_page`: số trang **PDF vật lý** (1-based) nơi đoạn evidence bắt đầu.
- `alt_gold`: các nguồn hợp lệ khác (thường là điều tương ứng ở bộ luật còn lại khi đáp án giống nhau). Hit với gold chính hoặc bất kỳ `alt_gold` nào đều tính là hit.
- `filter`: `null` hoặc `{"version": "2012"|"2019"}` — chỉ đặt khi **chính câu hỏi** nêu năm của bộ luật (filter do người hỏi cung cấp trước khi truy xuất, không lấy từ gold).
- `type`: `truc_tiep` (hỏi thẳng), `dien_dat_lai` (dùng từ ngữ khác văn bản), `dieu_kien` (điều kiện/ngoại lệ), `phien_ban` (đáp án khác nhau giữa hai bộ luật → có filter).

## Quy tắc phiên bản

Câu **không** filter phải có đáp án giống nhau ở cả hai bộ luật (khi đó ghi cả hai nguồn) hoặc nội dung chỉ có ở một bộ luật (q08 chỉ có ở 2019; q13 chỉ có ở 2012). Không dùng câu mơ hồ giữa hai phiên bản.

## Cách chia dev/test (chốt trước mọi lần chạy truy xuất)

- Test (q16–q20) chọn các chủ đề không có trong dev: thời hạn hợp đồng xác định thời hạn, lương thử việc, thời hiệu kỷ luật, cho thuê lại lao động, lao động chưa thành niên.
- Có 5 câu filter (q06, q07, q11, q15 ở dev; q16 ở test).
- **Nguy cơ rò rỉ:** một số câu test cùng chương với câu dev (q16 với q13 — chương hợp đồng; q18 với q14 — chương kỷ luật). Vì chỉ có 2 tài liệu cùng cấu trúc, không thể tách hoàn toàn theo tài liệu; test 5 câu chỉ mang tính minh họa.

## Tiêu chí chọn chiến lược (chốt trước khi xem test)

1. Evidence Hit@3 trên dev cao nhất;
2. hòa → Hit@1 trên dev;
3. hòa → coherence trung bình cao hơn;
4. hòa → ít chunk / thời gian ingest thấp hơn.

Chọn xong mới chạy `evaluate --split test`; không sửa câu hỏi, split hay tham số sau khi xem test.

## Nguồn gốc câu hỏi

Câu hỏi do AI (Claude) soạn nháp từ văn bản đã trích xuất, kèm script tự xác định trang (`starter/scripts/draft_benchmark.py`); tác giả (Bùi Thái Sỹ) đã tự mở PDF kiểm từng evidence và chỉnh sửa trước khi chốt — xem mục "Nhật ký duyệt" bên dưới.

## Nhật ký duyệt (tác giả điền)

- Ngày chốt: 14/11/2026 (sha256 của `questions.jsonl` ghi trong `frozen.json`; `evaluate` từ chối chạy nếu file bị sửa).
- Câu đã viết lại / thay: 0
- Kiểm tự động: `python -m src.run check-benchmark` → `0 problems`, tức mỗi `evidence_quote` đều nằm nguyên văn (sau chuẩn hóa NFC + khoảng trắng) trong trang gold.
- Kiểm thủ công: mở PDF tại trang gold (và trang `alt_gold`), đối chiếu (1) evidence nằm đúng trang, (2) đúng số Điều, (3) `expected_answer` khớp nội dung Điều, (4) câu không filter có đáp án giống nhau ở hai bộ luật, câu có filter thì đáp án thật sự khác giữa 2012 và 2019.

Trang là **trang PDF vật lý** (1-based). Cột "Duyệt tay" do tác giả đánh dấu sau khi tự mở PDF.

| ID | Split | Gold (tài liệu · trang · Điều) | Alt gold | Evidence (đầu đoạn) | Duyệt tay | Ghi chú |
|---|---|---|---|---|---|---|
| q01 | dev | 2019 · tr.44 · Đ.105 | 2012 · tr.36 · Đ.104 | "Thời giờ làm việc bình thường không quá 08 giờ trong 01 ngày…" | ✅ | |
| q02 | dev | 2019 · tr.44 · Đ.106 | 2012 · tr.37 · Đ.105 | "Giờ làm việc ban đêm được tính từ 22 giờ đến 06 giờ sáng…" | ✅ | |
| q03 | dev | 2019 · tr.42 · Đ.98 | 2012 · tr.34 · Đ.97 | "Vào ngày nghỉ hằng tuần, ít nhất bằng 200%" | ✅ | |
| q04 | dev | 2019 · tr.57 · Đ.139 | 2012 · tr.54 · Đ.157 | "Trường hợp lao động nữ sinh đôi trở lên thì tính từ con thứ 02…" | ✅ | |
| q05 | dev | 2019 · tr.47 · Đ.113 | 2012 · tr.38 · Đ.111 | "12 ngày làm việc đối với người làm công việc trong điều kiện bình thường" | ✅ | |
| q06 | dev | 2012 · tr.37 · Đ.106 | — (filter 2012) | "không quá 30 giờ trong 01 tháng và tổng số không quá 200 giờ…" | ✅ | |
| q07 | dev | 2019 · tr.11 · Đ.25 | — (filter 2019) | "Không quá 180 ngày đối với công việc của người quản lý doanh nghiệp" | ✅ | |
| q08 | dev | 2019 · tr.16 · Đ.35 | — (chỉ có ở 2019) | "Người lao động có quyền đơn phương chấm dứt hợp đồng lao động không cần báo trước…" | ✅ | |
| q09 | dev | 2019 · tr.21 · Đ.46 | 2012 · tr.18 · Đ.48 | "mỗi năm làm việc được trợ cấp một nửa tháng tiền lương" | ✅ | |
| q10 | dev | 2019 · tr.46 · Đ.109 | 2012 · tr.38 · Đ.108 | "từ 06 giờ trở lên trong một ngày thì được nghỉ giữa giờ ít nhất 30 phút" | ✅ | |
| q11 | dev | 2019 · tr.46 · Đ.112 | — (filter 2019) | "Quốc khánh: 02 ngày (ngày 02 tháng 9 dương lịch và 01 ngày liền kề…)" | ✅ | |
| q12 | dev | 2019 · tr.57 · Đ.139 | 2012 · tr.54 · Đ.157 | "thời gian nghỉ trước khi sinh không quá 02 tháng" | ✅ | |
| q13 | dev | 2012 · tr.9 · Đ.22 | — (chỉ có ở 2012) | "Không được giao kết hợp đồng lao động theo mùa vụ hoặc theo một công việc…" | ✅ | |
| q14 | dev | 2019 · tr.51 · Đ.124 | 2012 · tr.43 · Đ.125 | "1. Khiển trách. 2. Kéo dài thời hạn nâng lương không quá 06 tháng. 3. …" | ✅ | |
| q15 | dev | 2012 · tr.63 · Đ.187 | — (filter 2012) | "được hưởng lương hưu khi nam đủ 60 tuổi, nữ đủ 55 tuổi" | ✅ | |
| q16 | test | 2019 · tr.9 · Đ.20 | — (filter 2019) | "trong thời gian không quá 36 tháng kể từ thời điểm có hiệu lực…" | ✅ | |
| q17 | test | 2019 · tr.12 · Đ.26 | 2012 · tr.11 · Đ.28 | "nhưng ít nhất phải bằng 85% mức lương của công việc đó" | ✅ | |
| q18 | test | 2019 · tr.51 · Đ.123 | 2012 · tr.43 · Đ.124 | "bí mật công nghệ, bí mật kinh doanh của người sử dụng lao động thì thời hiệu…" | ✅ | |
| q19 | test | 2019 · tr.23 · Đ.53 | 2012 · tr.21 · Đ.54 | "Thời hạn cho thuê lại lao động đối với người lao động tối đa là 12 tháng" | ✅ | |
| q20 | test | 2019 · tr.58 · Đ.143 | 2012 · tr.55 · Đ.161 | "Lao động chưa thành niên là người lao động chưa đủ 18 tuổi" | ✅ | |
