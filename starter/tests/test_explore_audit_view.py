import csv

from src.explore.audit_view import by_position, coherence_summary, load_rows

FIELDS = ["position_id", "document_id", "pdf_page", "position_text", "strategy", "chunk_id", "chunk_text",
          "score_0_2", "reason"]


def write(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def row(pid, s, score, **kw):
    return {"position_id": pid, "document_id": "d", "pdf_page": "5", "position_text": "t", "strategy": s,
            "chunk_id": f"{s}:{pid}", "chunk_text": "x", "score_0_2": score, "reason": "r", **kw}


def test_missing_file_gives_empty_rows(tmp_path):
    assert load_rows(tmp_path / "nope.csv") == []


def test_summary_mean_counts_and_ignores_blank(tmp_path):
    write(tmp_path / "c.csv", [row("p1", "A", "0"), row("p2", "A", "1"), row("p3", "A", ""),
                               row("p1", "B", "2"), row("p2", "B", "2")])
    s = {r["strategy"]: r for r in coherence_summary(load_rows(tmp_path / "c.csv"))}
    assert s["A"]["n"] == 2 and s["A"]["mean"] == 0.5 and s["A"]["phân bố"] == "0:1 1:1 2:0"
    assert s["B"]["n"] == 2 and s["B"]["mean"] == 2.0


def test_summary_empty_when_nothing_scored(tmp_path):
    write(tmp_path / "c.csv", [row("p1", "A", "")])
    assert coherence_summary(load_rows(tmp_path / "c.csv")) == []


def test_by_position_groups_strategies_in_file_order(tmp_path):
    write(tmp_path / "c.csv", [row("p1", "A", "1"), row("p1", "B", "2"), row("p2", "A", "0")])
    pos = by_position(load_rows(tmp_path / "c.csv"))
    assert [p["position_id"] for p in pos] == ["p1", "p2"]
    assert set(pos[0]["rows"]) == {"A", "B"} and pos[0]["rows"]["B"]["score_0_2"] == "2"
