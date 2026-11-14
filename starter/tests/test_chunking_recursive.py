from src.chunking import build_stream
from src.chunking_extra import recursive
from tests.conftest import make_page


def _line_pages():
    lines = [f"Dòng {i:02d} " + "nội dung ngắn " * 6 for i in range(30)]
    return [make_page(1, "\n".join(lines[:15])), make_page(2, "\n".join(lines[15:]))], lines


def test_recursive_max_size(synthetic_pages):
    chunks = recursive(synthetic_pages, size=800, overlap=100)
    assert len(chunks) >= 3 and all(len(c.text) <= 800 for c in chunks)


def test_recursive_prefers_line_breaks():
    pages, lines = _line_pages()
    chunks = recursive(pages, size=800, overlap=100)
    line_set = {ln.strip() for ln in lines}
    for c in chunks[:-1]:
        assert c.text.splitlines()[-1].strip() in line_set, "chunk must end on a whole line"


def test_recursive_does_not_start_mid_word(synthetic_pages):
    stream, _ = build_stream(synthetic_pages)
    words = set(stream.split())
    for c in recursive(synthetic_pages, size=800, overlap=100):
        assert c.text.split()[0] in words


def test_recursive_covers_all_text(synthetic_pages):
    stream, _ = build_stream(synthetic_pages)
    chunks = recursive(synthetic_pages, size=800, overlap=100)
    assert set(stream.split()) <= {w for c in chunks for w in c.text.split()}


def test_recursive_ids_stable_and_hash(synthetic_pages):
    a = recursive(synthetic_pages)
    b = recursive(synthetic_pages)
    assert [(c.chunk_id, c.metadata["content_hash"]) for c in a] == [(c.chunk_id, c.metadata["content_hash"]) for c in b]
    assert a[0].chunk_id == "D:blld-2019:0000"


def test_recursive_page_and_structure_metadata(synthetic_pages):
    chunks = recursive(synthetic_pages, size=200, overlap=20)
    last = chunks[-1]
    assert last.metadata["strategy"] == "D" and last.metadata["version"] == "2019"
    assert last.metadata["dieu"] == 3 and last.metadata["chuong"] == "Chương II"
    assert last.metadata["page_start"] <= last.metadata["page_end"] <= 3
    assert chunks[0].metadata["page_start"] == 1 and chunks[0].metadata["printed_page_start"] == 3
