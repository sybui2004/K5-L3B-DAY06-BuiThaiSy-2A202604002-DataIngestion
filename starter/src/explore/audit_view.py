"""Read-only views over the manual-audit CSVs (labels are written by hand, never by the app)."""
import csv
from collections import defaultdict
from pathlib import Path


def load_rows(path: Path) -> list[dict]:
    """Rows of an audit CSV; [] when the file does not exist yet."""
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def coherence_summary(rows: list[dict]) -> list[dict]:
    """Per strategy: number of scored positions, mean /2 and the 0/1/2 distribution (blank scores ignored)."""
    scores: dict[str, list[int]] = defaultdict(list)
    for r in rows:
        if r.get("score_0_2", "").strip() != "":
            scores[r["strategy"]].append(int(r["score_0_2"]))
    return [{"strategy": s, "n": len(v), "mean": round(sum(v) / len(v), 2),
             "phân bố": " ".join(f"{k}:{v.count(k)}" for k in (0, 1, 2))} for s, v in sorted(scores.items())]


def by_position(rows: list[dict]) -> list[dict]:
    """[{'position_id', 'position_text', 'rows': {strategy: row}}] in file order."""
    grouped: dict[str, dict] = {}
    for r in rows:
        g = grouped.setdefault(r["position_id"], {"position_id": r["position_id"],
                                                  "position_text": r.get("position_text", ""), "rows": {}})
        g["rows"][r["strategy"]] = r
    return list(grouped.values())
