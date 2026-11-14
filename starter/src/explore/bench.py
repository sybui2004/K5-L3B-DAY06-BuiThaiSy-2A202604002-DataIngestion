"""Dev-only benchmark for exploration strategies; writes under results/explore/ and never touches submission files."""
import csv
import json
from datetime import datetime
from pathlib import Path

from ..config import EXPLORE_DIR, TOP_K
from ..evaluation import run_strategy, summarize
from ..run import assert_frozen

FIELDS = ["strategy", "n", "hit1", "hit3", "evaluated_at"]


def run_explore_benchmark(strategy: str, questions: list[dict], store, embedder,
                          out_dir: Path = EXPLORE_DIR) -> list[dict]:
    assert_frozen()
    bad = [q["id"] for q in questions if q["split"] != "dev"]
    if bad:
        raise ValueError(f"exploration benchmark runs on the dev split only; got non-dev questions {bad}")
    traces = run_strategy(strategy, questions, store, embedder, top_k=TOP_K)
    (out_dir / "traces").mkdir(parents=True, exist_ok=True)
    with (out_dir / "traces" / f"{strategy}_dev.jsonl").open("w", encoding="utf-8") as fh:
        for t in traces:
            fh.write(json.dumps(t, ensure_ascii=False) + "\n")
    metrics = out_dir / "metrics.csv"
    rows = {r["strategy"]: r for r in csv.DictReader(metrics.open(encoding="utf-8"))} if metrics.exists() else {}
    s = summarize(traces)[0]
    rows[strategy] = {"strategy": strategy, "n": s["n"], "hit1": s["hit1"], "hit3": s["hit3"],
                      "evaluated_at": datetime.now().isoformat(timespec="seconds")}
    with metrics.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows[k] for k in sorted(rows))
    return traces
