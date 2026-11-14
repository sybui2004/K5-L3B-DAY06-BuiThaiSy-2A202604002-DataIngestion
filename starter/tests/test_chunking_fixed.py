from src.chunking import build_stream, fixed_size


def test_fixed_sizes_and_overlap(synthetic_pages):
    chunks = fixed_size(synthetic_pages, size=800, overlap=100)
    assert len(chunks) >= 3
    assert all(len(c.text) <= 800 for c in chunks)
    for prev, cur in zip(chunks, chunks[1:]):
        assert cur.text[:100] == prev.text[-100:]


def test_fixed_page_span(synthetic_pages):
    stream, spans = build_stream(synthetic_pages)
    chunks = fixed_size(synthetic_pages, size=800, overlap=100)
    crossing = [c for c in chunks if c.metadata["page_start"] == 1 and c.metadata["page_end"] == 2]
    assert crossing, "a chunk spanning pages 1-2 must record both pages"
    assert crossing[0].page == 1 and crossing[0].metadata["printed_page_start"] == 3


def test_fixed_structure_metadata(synthetic_pages):
    chunks = fixed_size(synthetic_pages, size=800, overlap=100)
    last = chunks[-1]
    assert last.metadata["dieu"] == 3 and last.metadata["chuong"] == "Chương II"
    assert last.metadata["dieu_title"] == "Hợp đồng"
    assert all(c.metadata["strategy"] == "A" and c.metadata["version"] == "2019" for c in chunks)


def test_fixed_ids_stable(synthetic_pages):
    a = fixed_size(synthetic_pages, size=800, overlap=100)
    b = fixed_size(synthetic_pages, size=800, overlap=100)
    assert [(c.chunk_id, c.metadata["content_hash"]) for c in a] == [(c.chunk_id, c.metadata["content_hash"]) for c in b]
    assert a[0].chunk_id == "A:blld-2019:0000"


def test_skips_non_content_pages(synthetic_pages):
    from tests.conftest import make_page
    pages = synthetic_pages + [make_page(4, "")]
    chunks = fixed_size(pages, size=800, overlap=100)
    assert all(c.metadata["page_end"] <= 3 for c in chunks)
