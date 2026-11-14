"""One-off helper: write the AI-drafted benchmark, locating each evidence quote's PDF page automatically.

The author reviews/edits benchmark/questions.jsonl afterwards; this script is kept only as provenance.
Run from starter/: python scripts/draft_benchmark.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.config import BENCHMARK_PATH  # noqa: E402
from src.evaluation import squash  # noqa: E402
from src.run import load_corpus  # noqa: E402

P = load_corpus()
L19, L12 = "blld-2019", "blld-2012"


def page_of(doc: str, quote: str) -> int:
    pages, q = P[doc], squash(quote)
    for p in pages:
        if q in squash(p.text):
            return p.page
    for p, nxt in zip(pages, pages[1:]):
        if q in squash(p.text) + squash(nxt.text):
            return p.page
    raise SystemExit(f"NOT FOUND {doc}: {quote}")


def Q(qid, split, typ, question, answer, gold, alts=(), flt=None):
    doc, dieu, quote = gold
    return {"id": qid, "split": split, "type": typ, "question": question, "expected_answer": answer,
            "gold_source_id": doc, "gold_page": page_of(doc, quote), "gold_dieu": dieu, "evidence_quote": quote,
            "alt_gold": [{"source_id": d, "page": page_of(d, t), "dieu": n, "evidence_quote": t} for d, n, t in alts],
            "filter": {"version": flt} if flt else None}


QUESTIONS = [
    Q("q01", "dev", "truc_tiep", "Thời giờ làm việc bình thường tối đa là bao nhiêu giờ một ngày và bao nhiêu giờ một tuần?",
      "Không quá 08 giờ/ngày và 48 giờ/tuần (cả hai Bộ luật).",
      (L19, 105, "Thời giờ làm việc bình thường không quá 08 giờ trong 01 ngày và không quá 48 giờ trong 01 tuần"),
      [(L12, 104, "Thời giờ làm việc bình thường không quá 08 giờ trong 01 ngày và 48 giờ trong 01 tuần")]),
    Q("q02", "dev", "dien_dat_lai", "Ca làm đêm được tính bắt đầu từ mấy giờ và kết thúc lúc nào?",
      "Từ 22 giờ đến 06 giờ sáng ngày hôm sau.",
      (L19, 106, "Giờ làm việc ban đêm được tính từ 22 giờ đến 06 giờ sáng ngày hôm sau"),
      [(L12, 105, "Giờ làm việc ban đêm được tính từ 22 giờ đến 6 giờ sáng ngày hôm sau")]),
    Q("q03", "dev", "truc_tiep", "Làm thêm giờ vào ngày nghỉ hằng tuần thì được trả lương ít nhất bằng bao nhiêu phần trăm?",
      "Ít nhất bằng 200%.",
      (L19, 98, "Vào ngày nghỉ hằng tuần, ít nhất bằng 200%"),
      [(L12, 97, "Vào ngày nghỉ hàng tuần, ít nhất bằng 200%")]),
    Q("q04", "dev", "dieu_kien", "Lao động nữ sinh đôi thì thời gian nghỉ thai sản được cộng thêm như thế nào?",
      "Từ con thứ 02 trở đi, mỗi con người mẹ được nghỉ thêm 01 tháng (ngoài 06 tháng).",
      (L19, 139, "Trường hợp lao động nữ sinh đôi trở lên thì tính từ con thứ 02 trở đi, cứ mỗi con, người mẹ được nghỉ thêm 01 tháng"),
      [(L12, 157, "Trường hợp lao động nữ sinh đôi trở lên thì tính từ con thứ 02 trở đi, cứ mỗi con, người mẹ được nghỉ thêm 01 tháng")]),
    Q("q05", "dev", "truc_tiep", "Người làm công việc trong điều kiện bình thường được nghỉ hằng năm bao nhiêu ngày?",
      "12 ngày làm việc (khi đủ 12 tháng làm việc).",
      (L19, 113, "12 ngày làm việc đối với người làm công việc trong điều kiện bình thường"),
      [(L12, 111, "12 ngày làm việc đối với người làm công việc trong điều kiện bình thường")]),
    Q("q06", "dev", "phien_ban", "Theo Bộ luật Lao động 2012, số giờ làm thêm tối đa trong một tháng là bao nhiêu?",
      "Không quá 30 giờ/tháng (tổng không quá 200 giờ/năm, trường hợp đặc biệt 300 giờ).",
      (L12, 106, "không quá 30 giờ trong 01 tháng và tổng số không quá 200 giờ trong 01 năm"), flt="2012"),
    Q("q07", "dev", "phien_ban", "Theo Bộ luật Lao động 2019, thời gian thử việc tối đa đối với người quản lý doanh nghiệp là bao lâu?",
      "Không quá 180 ngày.",
      (L19, 25, "Không quá 180 ngày đối với công việc của người quản lý doanh nghiệp"), flt="2019"),
    Q("q08", "dev", "dieu_kien", "Trong trường hợp nào người lao động được nghỉ việc ngay mà không cần báo trước cho người sử dụng lao động?",
      "Không được bố trí đúng công việc/địa điểm; không được trả đủ hoặc đúng hạn lương; bị ngược đãi; bị quấy rối tình dục; "
      "lao động nữ mang thai phải nghỉ; đủ tuổi nghỉ hưu; người sử dụng lao động cung cấp thông tin không trung thực (Điều 35 BLLĐ 2019).",
      (L19, 35, "Người lao động có quyền đơn phương chấm dứt hợp đồng lao động không cần báo trước trong trường hợp sau đây")),
    Q("q09", "dev", "truc_tiep", "Trợ cấp thôi việc được tính bao nhiêu cho mỗi năm làm việc?",
      "Mỗi năm làm việc được trợ cấp một nửa tháng tiền lương.",
      (L19, 46, "mỗi năm làm việc được trợ cấp một nửa tháng tiền lương"),
      [(L12, 48, "mỗi năm làm việc được trợ cấp một nửa tháng tiền lương")]),
    Q("q10", "dev", "dien_dat_lai", "Nhân viên làm việc từ 6 tiếng trở lên mỗi ngày được nghỉ giữa ca tối thiểu bao nhiêu phút?",
      "Ít nhất 30 phút (làm ban đêm ít nhất 45 phút).",
      (L19, 109, "từ 06 giờ trở lên trong một ngày thì được nghỉ giữa giờ ít nhất 30 phút"),
      [(L12, 108, "được nghỉ giữa giờ ít nhất 30 phút, tính vào thời giờ làm việc")]),
    Q("q11", "dev", "phien_ban", "Theo Bộ luật Lao động 2019, người lao động được nghỉ mấy ngày dịp Quốc khánh?",
      "02 ngày (ngày 02/9 và 01 ngày liền kề trước hoặc sau).",
      (L19, 112, "Quốc khánh: 02 ngày (ngày 02 tháng 9 dương lịch và 01 ngày liền kề trước hoặc sau)"), flt="2019"),
    Q("q12", "dev", "truc_tiep", "Lao động nữ được nghỉ trước khi sinh con tối đa bao lâu?",
      "Không quá 02 tháng.",
      (L19, 139, "thời gian nghỉ trước khi sinh không quá 02 tháng"),
      [(L12, 157, "Thời gian nghỉ trước khi sinh tối đa không quá 02 tháng")]),
    Q("q13", "dev", "dieu_kien", "Có được ký hợp đồng mùa vụ dưới 12 tháng để làm công việc có tính chất thường xuyên từ 12 tháng trở lên không?",
      "Không, trừ khi tạm thời thay thế người đi nghĩa vụ quân sự, nghỉ thai sản, ốm đau, tai nạn lao động hoặc nghỉ tạm thời khác (Điều 22 BLLĐ 2012).",
      (L12, 22, "Không được giao kết hợp đồng lao động theo mùa vụ hoặc theo một công việc nhất định có thời hạn dưới 12 tháng "
                "để làm những công việc có tính chất thường xuyên từ 12 tháng trở lên")),
    Q("q14", "dev", "truc_tiep", "Có những hình thức xử lý kỷ luật lao động nào?",
      "Khiển trách; kéo dài thời hạn nâng lương không quá 06 tháng; cách chức; sa thải.",
      (L19, 124, "1. Khiển trách. 2. Kéo dài thời hạn nâng lương không quá 06 tháng. 3. Cách chức. 4. Sa thải."),
      [(L12, 125, "1. Khiển trách. 2. Kéo dài thời hạn nâng lương không quá 06 tháng; cách chức. 3. Sa thải.")]),
    Q("q15", "dev", "phien_ban", "Theo Bộ luật Lao động 2012, lao động nữ được hưởng lương hưu khi đủ bao nhiêu tuổi?",
      "Nữ đủ 55 tuổi (nam đủ 60 tuổi).",
      (L12, 187, "được hưởng lương hưu khi nam đủ 60 tuổi, nữ đủ 55 tuổi"), flt="2012"),
    Q("q16", "test", "phien_ban", "Theo Bộ luật Lao động 2019, hợp đồng lao động xác định thời hạn được ký với thời hạn tối đa bao lâu?",
      "Không quá 36 tháng kể từ thời điểm có hiệu lực.",
      (L19, 20, "trong thời gian không quá 36 tháng kể từ thời điểm có hiệu lực của hợp đồng"), flt="2019"),
    Q("q17", "test", "truc_tiep", "Trong thời gian thử việc, người lao động được trả lương tối thiểu bao nhiêu?",
      "Ít nhất bằng 85% mức lương của công việc đó.",
      (L19, 26, "nhưng ít nhất phải bằng 85% mức lương của công việc đó"),
      [(L12, 28, "nhưng ít nhất phải bằng 85% mức lương của công việc đó")]),
    Q("q18", "test", "dieu_kien", "Nếu hành vi vi phạm liên quan đến bí mật kinh doanh thì thời hiệu xử lý kỷ luật lao động là bao lâu?",
      "12 tháng (thay vì 06 tháng thông thường).",
      (L19, 123, "bí mật công nghệ, bí mật kinh doanh của người sử dụng lao động thì thời hiệu xử lý kỷ luật lao động là 12 tháng"),
      [(L12, 124, "bí mật công nghệ, bí mật kinh doanh của người sử dụng lao động thì thời hiệu xử lý kỷ luật lao động tối đa là 12 tháng")]),
    Q("q19", "test", "dien_dat_lai", "Một doanh nghiệp được cho thuê lại một người lao động trong thời gian dài nhất là bao lâu?",
      "Tối đa 12 tháng.",
      (L19, 53, "Thời hạn cho thuê lại lao động đối với người lao động tối đa là 12 tháng"),
      [(L12, 54, "Thời hạn cho thuê lại lao động tối đa không quá 12 tháng")]),
    Q("q20", "test", "truc_tiep", "Người lao động ở độ tuổi nào thì được coi là lao động chưa thành niên?",
      "Chưa đủ 18 tuổi (dưới 18 tuổi).",
      (L19, 143, "Lao động chưa thành niên là người lao động chưa đủ 18 tuổi"),
      [(L12, 161, "Người lao động chưa thành niên là người lao động dưới 18 tuổi")]),
]

if __name__ == "__main__":
    BENCHMARK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with BENCHMARK_PATH.open("w", encoding="utf-8") as fh:
        for q in QUESTIONS:
            fh.write(json.dumps(q, ensure_ascii=False) + "\n")
    print(f"wrote {len(QUESTIONS)} questions to {BENCHMARK_PATH}")
