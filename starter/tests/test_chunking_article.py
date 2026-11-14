import pytest

from src import config
from src.chunking import by_article
from src.ingestion import load_pdf
from tests.conftest import make_page


def test_one_chunk_per_short_article(synthetic_pages):
    chunks = by_article(synthetic_pages, max_size=1500)
    assert [c.metadata["dieu"] for c in chunks] == [1, 2, 3]
    assert all(c.text.startswith("Điều ") for c in chunks)
    assert chunks[0].chunk_id == "B:blld-2019:d001-p1"


def test_preamble_and_chapter_not_chunks(synthetic_pages):
    pages = [make_page(1, "Căn cứ Hiến pháp;\nQuốc hội ban hành Bộ luật.\n" + synthetic_pages[0].text)] + synthetic_pages[1:]
    chunks = by_article(pages, max_size=1500)
    assert not any(c.text.startswith(("Căn cứ", "Chương")) for c in chunks)
    assert chunks[0].metadata["chuong"] == "Chương I"
    assert "Chương II" not in chunks[1].text and "HỢP ĐỒNG" not in chunks[1].text
    assert chunks[2].metadata["chuong"] == "Chương II"


def test_long_article_split_by_clause():
    clauses = [f"{i}. " + (f"Khoản {i} nội dung. " * 32) for i in range(1, 5)]
    page = make_page(1, "Điều 5. Thời giờ làm việc\n" + "\n".join(clauses))
    chunks = by_article([page], max_size=1500)
    assert len(chunks) >= 2
    assert all(len(c.text) <= 1500 for c in chunks)
    assert all(c.text.startswith("Điều 5. Thời giờ làm việc\n") for c in chunks)
    joined = "\n".join(c.text.split("\n", 1)[1] for c in chunks)
    assert [joined.find(f"{i}. Khoản {i}") for i in range(1, 5)] == sorted(joined.find(f"{i}. Khoản {i}") for i in range(1, 5))
    assert all(f"{i}. Khoản {i}" in joined for i in range(1, 5))


def test_single_huge_clause_split_by_sentence():
    sentences = [f"Câu số {i} nói về nghĩa vụ của người sử dụng lao động." for i in range(60)]
    page = make_page(1, "Điều 7. Nghĩa vụ\n1. " + " ".join(sentences))
    chunks = by_article([page], max_size=1500)
    assert all(len(c.text) <= 1500 for c in chunks)
    body = " ".join(c.text for c in chunks)
    assert all(s in body for s in sentences)


@pytest.mark.parametrize("doc_index,last", [(0, 242), (1, 220)])
def test_real_article_coverage(doc_index, last):
    d = config.DOCUMENTS[doc_index]
    pages = load_pdf(config.DATA_RAW / d["filename"], d["document_id"], d["filename"], d["version"])
    found = {c.metadata["dieu"] for c in by_article(pages)}
    missing = sorted(set(range(1, last + 1)) - found)
    assert not missing, f"missing articles: {missing[:20]}"
    assert max(found) == last
