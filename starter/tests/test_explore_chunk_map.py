from src.explore.chunk_map import length_histogram, page_rows


def _c(cid, p0, p1, n, dieu=1):
    return {"chunk_id": cid, "text": "x" * n, "metadata": {"page_start": p0, "page_end": p1, "char_count": n, "dieu": dieu}}


def test_rows_sorted_by_page_then_id():
    rows = page_rows([_c("B:2", 5, 5, 10), _c("B:1", 5, 6, 20), _c("A:0", 1, 1, 30)])
    assert [r["chunk_id"] for r in rows] == ["A:0", "B:1", "B:2"]
    assert set(rows[0]) == {"chunk_id", "page_start", "page_end", "char_count", "dieu"}


def test_histogram_counts_sum_to_n():
    chunks = [_c(f"c{i}", 1, 1, n) for i, n in enumerate([10, 20, 200, 800, 801, 1500])]
    hist = length_histogram(chunks, bins=5)
    assert len(hist) == 5 and sum(c for _, c in hist) == 6


def test_histogram_empty_list_ok():
    assert length_histogram([], bins=5) == []


def test_map_html_groups_by_document_and_escapes():
    from src.explore.chunk_map import map_html
    rows = [{"chunk_id": "B:blld-2019:d001-p1", "page_start": 1, "page_end": 1, "char_count": 100, "dieu": 1},
            {"chunk_id": "B:blld-2012:d<b>", "page_start": 2, "page_end": 2, "char_count": 900, "dieu": 2}]
    html = map_html(rows)
    assert "blld-2019" in html and "blld-2012" in html and "B:blld-2019:d001-p1" in html
    assert "<b>" not in html and "&lt;b&gt;" in html


def test_map_html_empty():
    from src.explore.chunk_map import map_html
    assert map_html([]) == ""
