"""Data for the chunk map tab: where chunks sit on pages and how long they are."""


def page_rows(chunks: list[dict]) -> list[dict]:
    rows = [{"chunk_id": c["chunk_id"], "page_start": c["metadata"]["page_start"],
             "page_end": c["metadata"]["page_end"],
             "char_count": c["metadata"].get("char_count") or len(c["text"]),
             "dieu": c["metadata"].get("dieu")} for c in chunks]
    return sorted(rows, key=lambda r: (r["page_start"], r["chunk_id"]))


def length_histogram(chunks: list[dict], bins: int = 10) -> list[tuple[int, int]]:
    """[(bin_lower_bound, count)] over chunk lengths; [] when there are no chunks."""
    lengths = [c["metadata"].get("char_count") or len(c["text"]) for c in chunks]
    if not lengths:
        return []
    lo, hi = min(lengths), max(lengths)
    width = max(1, -(-(hi - lo + 1) // bins))
    counts = [0] * bins
    for n in lengths:
        counts[min((n - lo) // width, bins - 1)] += 1
    return [(lo + i * width, c) for i, c in enumerate(counts)]


def map_html(rows: list[dict]) -> str:
    """Strip of coloured boxes: one block per page, one box per chunk starting there; colour = length."""
    import html
    if not rows:
        return ""
    longest = max(r["char_count"] for r in rows) or 1
    by_doc: dict[str, dict[int, list[dict]]] = {}
    for r in rows:
        by_doc.setdefault(r["chunk_id"].split(":")[1], {}).setdefault(r["page_start"], []).append(r)
    out = []
    for doc, pages in by_doc.items():
        out.append(f"<div style='margin:8px 0 2px;font-weight:600'>{html.escape(doc)}</div>"
                   "<div style='display:flex;flex-wrap:wrap;gap:3px'>")
        for page in sorted(pages):
            boxes = "".join(
                f"<div title='{html.escape(r['chunk_id'])} · {r['char_count']} ký tự · "
                f"trang {r['page_start']}-{r['page_end']}' style='width:14px;height:14px;border-radius:2px;"
                f"background:hsl(210,70%,{85 - 55 * r['char_count'] // longest}%)'></div>"
                for r in pages[page])
            out.append(f"<div style='display:flex;flex-direction:column;gap:2px;align-items:center'>"
                       f"<span style='font-size:9px;color:#888'>{page}</span>{boxes}</div>")
        out.append("</div>")
    return "".join(out)
