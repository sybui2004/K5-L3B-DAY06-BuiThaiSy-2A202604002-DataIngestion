"""Write data/manifest.csv: source, licence, page counting and checksums."""
import csv
import hashlib
from datetime import date
from pathlib import Path

from .config import DATA_RAW, DOCUMENTS, MIN_PAGE_CHARS
from .models import DocumentPage

LICENSE = ("Văn bản quy phạm pháp luật — không thuộc phạm vi bảo hộ quyền tác giả "
           "(khoản 2 Điều 15 Luật Sở hữu trí tuệ); bản đăng chính thức trên Công báo Chính phủ")
COUNT_RULE = f"trang PDF có >= {MIN_PAGE_CHARS} ký tự nội dung sau khi bỏ header Công báo và chuẩn hóa"
# Read from each law's own 'Hiệu lực thi hành' article (PDF page in brackets), not from the web.
EFFECTIVE_DATES = {
    "blld-2012": "01/05/2013 (Điều 240, trang PDF 82)",
    "blld-2019": "01/01/2021 (Điều 220, trang PDF 92)",
}
FIELDS = ["source_id", "title", "source_url", "license_or_permission", "accessed_at",
          "gazette_issue", "effective_date_from_text", "physical_pages", "counted_pages",
          "excluded_pages", "page_count_rule", "char_count", "sha256"]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_manifest(pages_by_doc: dict[str, list[DocumentPage]], path: Path,
                   effective_dates: dict[str, str] | None = None) -> None:
    effective_dates = effective_dates or EFFECTIVE_DATES
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        for doc in DOCUMENTS:
            pages = pages_by_doc[doc["document_id"]]
            counted = [p for p in pages if p.metadata["is_content"]]
            excluded = [p for p in pages if not p.metadata["is_content"]]
            writer.writerow({
                "source_id": doc["document_id"],
                "title": doc["title"],
                "source_url": doc["source_url"],
                "license_or_permission": LICENSE,
                "accessed_at": date(2026, 11, 13).isoformat(),
                "gazette_issue": doc["gazette_issue"],
                "effective_date_from_text": effective_dates[doc["document_id"]],
                "physical_pages": len(pages),
                "counted_pages": ";".join(str(p.page) for p in counted),
                "excluded_pages": ";".join(f"{p.page} ({p.metadata['char_count']} ký tự)" for p in excluded),
                "page_count_rule": COUNT_RULE,
                "char_count": sum(p.metadata["char_count"] for p in counted),
                "sha256": _sha256(DATA_RAW / doc["filename"]),
            })
