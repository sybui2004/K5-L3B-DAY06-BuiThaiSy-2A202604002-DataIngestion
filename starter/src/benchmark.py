"""Load and validate benchmark/questions.jsonl before any retrieval run."""
import json
from pathlib import Path

from .config import MIN_EVIDENCE_CHARS
from .evaluation import gold_entries, squash
from .models import DocumentPage

REQUIRED = ["id", "split", "question", "expected_answer", "gold_source_id", "gold_page", "evidence_quote", "filter"]
VERSIONS = {"2012", "2019"}


def load_questions(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def validate_questions(questions: list[dict], pages_by_doc: dict[str, list[DocumentPage]]) -> list[str]:
    errors = []
    ids = [q.get("id") for q in questions]
    if len(ids) != len(set(ids)):
        errors.append("duplicate question ids")
    for q in questions:
        qid = q.get("id", "?")
        missing = [k for k in REQUIRED if k not in q]
        if missing:
            errors.append(f"{qid}: missing fields {missing}")
            continue
        if q["split"] not in {"dev", "test"}:
            errors.append(f"{qid}: split must be dev or test")
        flt = q["filter"]
        if flt is not None:
            if set(flt) != {"version"} or flt.get("version") not in VERSIONS:
                errors.append(f"{qid}: filter must be null or {{'version': '2012'|'2019'}}")
            elif flt["version"] not in q["question"]:
                errors.append(f"{qid}: filter {flt['version']} is not stated in the question text")
        for g in gold_entries(q):
            quote = squash(g.get("evidence_quote", ""))
            if len(quote) < MIN_EVIDENCE_CHARS:
                errors.append(f"{qid}: evidence shorter than {MIN_EVIDENCE_CHARS} chars ({g.get('source_id')})")
                continue
            pages = {p.page: p for p in pages_by_doc.get(g["source_id"], [])}
            gold_pages = g["page"] if isinstance(g["page"], list) else [g["page"]]
            # evidence may continue onto the next page: check the gold page(s) joined
            text = squash("".join(pages[p].text for p in gold_pages if p in pages))
            nxt = pages.get(gold_pages[-1] + 1)
            if quote not in text and (nxt is None or quote not in text + squash(nxt.text)):
                errors.append(f"{qid}: evidence not found on {g['source_id']} page {g['page']}")
    dev = [q for q in questions if q.get("split") == "dev"]
    test = [q for q in questions if q.get("split") == "test"]
    if len(dev) < 15 or len(test) < 5:
        errors.append(f"need >=15 dev and >=5 test, got {len(dev)} dev / {len(test)} test")
    if sum(1 for q in questions if q.get("filter")) < 3:
        errors.append("need >=3 questions with a filter")
    if not any(q.get("filter") for q in test):
        errors.append("need >=1 test question with a filter")
    return errors
