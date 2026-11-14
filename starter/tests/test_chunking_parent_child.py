from collections import defaultdict

from src.chunking import by_article
from src.chunking_extra import parent_child


def test_children_within_size_and_inside_parent(synthetic_pages):
    children = parent_child(synthetic_pages, child_size=150)
    assert len(children) > len(by_article(synthetic_pages))
    assert all(len(c.text) <= 150 for c in children)
    assert all(c.text in c.metadata["parent_text"] for c in children)


def test_children_cover_parent(synthetic_pages):
    groups = defaultdict(list)
    for c in parent_child(synthetic_pages, child_size=150):
        groups[c.metadata["parent_id"]].append(c)
    parents = {p.chunk_id: p for p in by_article(synthetic_pages)}
    assert set(groups) == set(parents)
    for pid, kids in groups.items():
        assert set(parents[pid].text.split()) <= {w for k in kids for w in k.text.split()}


def test_child_parent_fields_present(synthetic_pages):
    parents = {p.chunk_id: p.text for p in by_article(synthetic_pages)}
    for c in parent_child(synthetic_pages, child_size=150):
        assert c.metadata["strategy"] == "F" and c.metadata["version"] == "2019"
        assert c.metadata["parent_text"] == parents[c.metadata["parent_id"]]
        assert c.metadata["dieu"] in (1, 2, 3) and c.metadata["page_start"] <= c.metadata["page_end"]


def test_child_ids_unique_and_stable(synthetic_pages):
    a = parent_child(synthetic_pages, child_size=150)
    b = parent_child(synthetic_pages, child_size=150)
    assert len({c.chunk_id for c in a}) == len(a)
    assert [(c.chunk_id, c.metadata["content_hash"]) for c in a] == [(c.chunk_id, c.metadata["content_hash"]) for c in b]
    assert a[0].chunk_id.startswith("F:blld-2019:d001-p1-c")
