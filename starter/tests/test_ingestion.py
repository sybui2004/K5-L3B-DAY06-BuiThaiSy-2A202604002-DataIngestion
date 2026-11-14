import unicodedata

import pytest

from src import config
from src.ingestion import load_pdf, normalize_text, strip_gazette_header


def test_glyph_fix_only_in_safe_context():
    assert "05-8-2012" in normalize_text("Ngày 05ộ8ộ2012")
    assert normalize_text("Độc lập Ị Tự do Ị Hạnh phúc") == "Độc lập - Tự do - Hạnh phúc"
    assert normalize_text("người lao động") == "người lao động"


def test_strip_header_returns_printed_page():
    text, printed = strip_gazette_header(" CÔNG BÁO/Số 993 + 994/Ngày 26-12-2019 43 \nĐiều 95. Trả lương")
    assert text.startswith("Điều 95.") and printed == 43
    text, printed = strip_gazette_header("4 CÔNG BÁO/Số 993 + 994/Ngày 26-12-2019 \n  \nthỏa thuận")
    assert text.startswith("thỏa thuận") and printed == 4


def test_nfc():
    nfd = unicodedata.normalize("NFD", "Điều luật")
    assert normalize_text(nfd) == unicodedata.normalize("NFC", "Điều luật")


@pytest.fixture(scope="module")
def real_pages():
    out = {}
    for d in config.DOCUMENTS:
        out[d["document_id"]] = load_pdf(config.DATA_RAW / d["filename"], d["document_id"], d["filename"], d["version"])
    return out


def test_load_real_pdfs(real_pages):
    p12, p19 = real_pages["blld-2012"], real_pages["blld-2019"]
    assert len(p12) == 83 and len(p19) == 94
    assert p19[93].metadata["is_content"] is False
    assert "Điều 1. Phạm vi điều chỉnh" in p19[0].text
    assert all("CÔNG BÁO/Số" not in p.text for p in p12 + p19)
    assert p19[0].metadata["printed_page"] == 3 and p19[0].page == 1


def test_manifest_rows(real_pages, tmp_path):
    import csv

    from src.manifest import write_manifest

    out = tmp_path / "manifest.csv"
    write_manifest(real_pages, out, effective_dates={"blld-2012": "x", "blld-2019": "y"})
    rows = {r["source_id"]: r for r in csv.DictReader(out.open(encoding="utf-8"))}
    assert set(rows) == {"blld-2012", "blld-2019"}
    assert rows["blld-2012"]["physical_pages"] == "83"
    assert len(rows["blld-2012"]["counted_pages"].split(";")) == 83
    assert len(rows["blld-2019"]["counted_pages"].split(";")) == 93
    assert rows["blld-2019"]["excluded_pages"].startswith("94")
    assert len(rows["blld-2019"]["sha256"]) == 64
    assert "Điều 15" in rows["blld-2019"]["license_or_permission"]


def test_strip_header_page_number_on_previous_line():
    text, printed = strip_gazette_header(" \n4 \nCÔNG BÁO/Số 993 + 994/Ngày 26-12-2019 \n  \nthỏa thuận")
    assert text.startswith("thỏa thuận") and printed == 4


def test_strip_header_page_number_on_next_line():
    text, printed = strip_gazette_header(" \n \nCÔNG BÁO/Số 475 + 476/Ngày 05-8-2012 \n3 \n \nQUỐC HỘI")
    assert text.startswith("QUỐC HỘI") and printed == 3


def test_extractor_keeps_syllables_intact(real_pages):
    total = sum(p.metadata["split_syllable_suspects"] for p in real_pages["blld-2019"])
    assert total < 200
