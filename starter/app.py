"""Retrieval Lab — demo UI. Run from starter/:  streamlit run app.py"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from src import config  # noqa: E402
from src.audit import summarize_audit  # noqa: E402
from src.evaluation import is_hit  # noqa: E402
from src.explore.audit_view import by_position, coherence_summary, load_rows  # noqa: E402
from src.explore import services  # noqa: E402
from src.explore.bench import run_explore_benchmark  # noqa: E402
from src.explore.chunk_map import length_histogram, map_html, page_rows  # noqa: E402
from src.explore.pdf_view import render_page  # noqa: E402
from src.strategies import STRATEGIES  # noqa: E402

st.set_page_config(page_title="Retrieval Lab", layout="wide")
st.title("Retrieval Lab — Bộ luật Lao động 2012 / 2019")

svc = services.get_services()
problems = [m for m in svc.health.values() if m]
if problems:
    for m in problems:
        st.error(m)
    st.stop()

store, embedder = svc.store, svc.embedder
counts = {c: store.count(c) for c in STRATEGIES}
questions = svc.questions
FILES = {d["document_id"]: d["filename"] for d in config.DOCUMENTS}
SAMPLES = {f"{q['id']} · {q['question'][:70]}": q for q in questions}


def label(code: str) -> str:
    s = STRATEGIES[code]
    return f"{code} · {s.name} — " + (f"{counts[code]} chunk" if counts[code] else "chưa nạp")


def pick_sample() -> None:
    q = SAMPLES.get(st.session_state.get("sample"))
    if q:
        st.session_state["question"] = q["question"]


def search(codes: list[str], question: str, year: str) -> dict:
    flt = {"version": year} if year != "Tất cả" else None
    vec = embedder.embed_query(question)
    return {"question": question, "filters": flt,
            "results": {c: store.search(c, vec, top_k=config.TOP_K, filters=flt) for c in codes}}


left, middle, right = st.columns([1.1, 2.2, 1.5])

with left:
    st.subheader("Chiến lược")
    strategy = st.radio("Chiến lược chunking", list(STRATEGIES), format_func=label, key="strategy")
    st.caption(STRATEGIES[strategy].description)
    if counts[strategy] == 0:
        st.info(f"Chiến lược {strategy} chưa được nạp. Chạy: `python -m src.run ingest --strategy {strategy}`")
    year = st.radio("Bộ lọc năm (phiên bản luật)", ["Tất cả", "2019", "2012"], key="year", horizontal=True)
    compare = st.multiselect("So sánh song song với", [c for c in STRATEGIES if c != strategy], key="compare",
                             format_func=label)

with middle:
    st.subheader("Truy xuất")
    st.selectbox("Câu mẫu từ benchmark", ["(tự nhập)"] + list(SAMPLES), key="sample", on_change=pick_sample)
    question = st.text_input("Câu hỏi", key="question")
    go = st.button("Truy xuất top-3", key="search", type="primary", disabled=counts[strategy] == 0)
    if go:
        if not question.strip():
            st.warning("Hãy nhập câu hỏi (hoặc chọn một câu mẫu).")
        else:
            codes = [strategy] + [c for c in compare if c != strategy]
            missing = [c for c in codes if counts[c] == 0]
            if missing:
                st.warning("Bỏ qua chiến lược chưa nạp: " + ", ".join(missing))
            run = search([c for c in codes if counts[c]], question.strip(), year)
            gold = next((q for q in questions if q["question"] == run["question"]), None)
            st.session_state["run"] = {**run, "gold": gold}

    run = st.session_state.get("run")
    options = []
    if run:
        if run["gold"]:
            st.caption(f"Câu benchmark {run['gold']['id']} — ✅ nghĩa là chunk chứa đủ bằng chứng.")
        cols = st.columns(len(run["results"]))
        for col, (code, hits) in zip(cols, run["results"].items()):
            with col:
                suffix = f" · lọc {run['filters']['version']}" if run["filters"] else ""
                st.markdown(f"**{label(code).split(' — ')[0]}**{suffix}")
                for rank, h in enumerate(hits, start=1):
                    options.append(f"{code} #{rank}")
                    md = h["metadata"]
                    ok = " ✅" if run["gold"] and is_hit(h, run["gold"]) else ""
                    st.markdown(f"**#{rank}** · **Luật {md['version']}** · Điều {md.get('dieu')} · "
                                f"tr.{md['page_start']} · {h['score']:.3f}{ok}")
                    st.write(h["text"][:400] + ("…" if len(h["text"]) > 400 else ""))
                    if h.get("parent_text"):
                        with st.expander("Văn bản cha (cả Điều)"):
                            st.write(h["parent_text"])

with right:
    st.subheader("Vì sao kết quả này?")
    if run and options:
        pick = st.selectbox("Xem chi tiết", options, key="detail")
        code, rank = pick.split(" #")
        h = run["results"][code][int(rank) - 1]
        md = h["metadata"]
        try:
            png, note = render_page(config.DATA_RAW / FILES[md["document_id"]], md["page_start"], h["text"])
            if png:
                st.image(png, caption=f"{md['document_id']} · trang PDF {md['page_start']}")
            if note:
                st.caption(note)
        except Exception as exc:  # noqa: BLE001 - the demo must keep running without the PDF image
            st.caption(f"Không hiển thị được trang PDF ({type(exc).__name__})")
        shown = run["results"][code]
        st.bar_chart(pd.DataFrame({"cosine": [x["score"] for x in shown]},
                                  index=[f"#{i}" for i in range(1, len(shown) + 1)]))
        st.table(pd.DataFrame({"trường": ["tài liệu", "phiên bản", "chương", "Điều", "trang PDF", "trang in"],
                               "giá trị": [md["document_id"], md["version"], md.get("chuong"), md.get("dieu"),
                                           f"{md['page_start']}-{md['page_end']}", md.get("printed_page_start")]}
                              ).astype(str))
    else:
        st.caption("Chạy một truy vấn để xem trang PDF được tô sáng, điểm và metadata.")

tab_bench, tab_map, tab_year, tab_audit, tab_db = st.tabs(
    ["Benchmark", "Bản đồ chunk", "Hiệu ứng bộ lọc năm", "Audit", "Dữ liệu DB"])
ingested = [c for c in STRATEGIES if counts[c]]

with tab_bench:
    st.markdown("Chạy **tập dev** để so sánh chiến lược. Kết quả khám phá lưu ở `results/explore/`, "
                "không ảnh hưởng số liệu nộp bài. Tập test không chạy ở đây.")
    st.markdown("\n".join(
        ["| Mã | Chiến lược | Cách cắt chunk | Loại |", "|---|---|---|---|"]
        + [f"| **{s.code}** | {s.name} | {s.description} | {'bài nộp' if s.official else 'khám phá'} |"
           for s in STRATEGIES.values()]))
    chosen = st.multiselect("Chiến lược", ingested, default=ingested[:1], key="bench_strategies",
                            format_func=label)
    if st.button("Chạy benchmark dev", key="run_bench"):
        dev = [q for q in questions if q["split"] == "dev"]
        try:
            for code in chosen:
                with st.spinner(f"Đang chạy {code}…"):
                    run_explore_benchmark(code, dev, store, embedder)
        except SystemExit as exc:
            st.error(str(exc))
    mpath = config.EXPLORE_DIR / "metrics.csv"
    if mpath.exists():
        explored = pd.read_csv(mpath)
        explored.insert(1, "tên", explored["strategy"].map(lambda c: STRATEGIES[c].name))
        st.dataframe(explored, hide_index=True)
        failing = []
        for code in ingested:
            tp = config.EXPLORE_DIR / "traces" / f"{code}_dev.jsonl"
            if tp.exists():
                failing += [(code, t) for t in map(json.loads, tp.read_text(encoding="utf-8").splitlines())
                            if not t["hit_at_3"]]
        if failing:
            names = [f"{c} · {t['question_id']} · {t['question'][:60]}" for c, t in failing]
            sel = st.selectbox("Câu truy xuất sai (xem top-3)", names, key="failing")
            for hit in failing[names.index(sel)][1]["top_k"]:
                st.markdown(f"**#{hit['rank']}** {hit['chunk_id']} · {hit['score']}")
                st.write(hit["text"][:300])
    official = config.RESULTS_DIR / "metrics.csv"
    if official.exists():
        st.markdown("**Số liệu nộp bài A/B/C (chỉ đọc)**")
        official_df = pd.read_csv(official)
        official_df.insert(1, "tên", official_df["strategy"].map(lambda c: STRATEGIES[c].name))
        st.dataframe(official_df, hide_index=True)

with tab_map:
    if ingested:
        code = st.selectbox("Chiến lược", ingested, key="map_strategy", format_func=label)
        chunks = store.all_chunks(code)
        st.markdown(map_html(page_rows(chunks)), unsafe_allow_html=True)
        hist = length_histogram(chunks)
        if hist:
            st.bar_chart(pd.DataFrame({"số chunk": [c for _, c in hist]}, index=[str(b) for b, _ in hist]))
    else:
        st.info("Chưa có chiến lược nào được nạp.")

with tab_year:
    base = st.selectbox("Chiến lược", ingested, key="year_strategy", format_func=label) if ingested else None
    q_text = st.session_state.get("question", "").strip()
    if base and q_text and st.button("So sánh có / không lọc năm", key="year_compare"):
        vec = embedder.embed_query(q_text)
        cols = st.columns(3)
        variants = [("Không lọc", None), ("version = 2019", {"version": "2019"}), ("version = 2012", {"version": "2012"})]
        for col, (title, flt) in zip(cols, variants):
            with col:
                st.markdown(f"**{title}**")
                for rank, h in enumerate(store.search(base, vec, top_k=config.TOP_K, filters=flt), start=1):
                    m = h["metadata"]
                    st.markdown(f"#{rank} · {m['version']} · Điều {m.get('dieu')} · tr.{m['page_start']} · {h['score']:.3f}")
    elif not q_text:
        st.info("Nhập câu hỏi ở khung Truy xuất rồi bấm nút để so sánh kết quả có/không lọc năm.")

with tab_audit:
    audit_dir = config.RESULTS_DIR / "audit"
    st.markdown("**Audit thủ công** (chỉ đọc): nhãn nằm trong các file CSV ở `results/audit/`; giao diện chỉ hiển thị.")
    coh = load_rows(audit_dir / "coherence.csv")
    if not coh:
        st.info("Chưa có `coherence.csv`. Tạo bằng `python -m src.run audit-templates`.")
    else:
        labelers = sorted({r["labeler"] for r in coh if r.get("labeler")})
        if labelers:
            st.warning("Nguồn nhãn coherence: " + "; ".join(labelers))
        st.markdown("**1. Chunk coherence** — thang 0–2 trên 10 vị trí nguồn (C dùng chung chunk với B)")
        summary = coherence_summary(coh)
        if summary:
            st.dataframe(pd.DataFrame(summary).assign(tên=lambda d: d["strategy"].map(lambda c: STRATEGIES[c].name)),
                         hide_index=True)
        else:
            st.info("Chưa có điểm nào được chấm (cột `score_0_2` đang trống).")
        positions = by_position(coh)
        pos_ids = [p["position_id"] for p in positions]
        chosen_pos = st.selectbox("Vị trí nguồn", pos_ids, key="audit_position")
        current = positions[pos_ids.index(chosen_pos)]
        st.caption("Vị trí: " + current["position_text"].replace("\n", " ⏎ "))
        for col, code in zip(st.columns(3), ["A", "B", "C"]):
            r = current["rows"].get(code)
            with col:
                if r:
                    st.markdown(f"**{label(code).split(' — ')[0]}** · điểm **{r['score_0_2'] or '—'}**")
                    st.caption(r["chunk_id"])
                    st.write(r["reason"] or "(chưa có lý do)")
                    with st.expander("Xem chunk"):
                        st.text(r["chunk_text"])
    meta_ok = (audit_dir / "metadata.csv").exists() and (audit_dir / "grounding.csv").exists()
    st.markdown("**2–3. Metadata và grounding** — chấm trên 5 câu test")
    if meta_ok:
        st.dataframe(pd.DataFrame(summarize_audit(audit_dir)), hide_index=True)
    else:
        st.info("Chưa có `metadata.csv` / `grounding.csv`: chúng được tạo sau khi chạy "
                "`evaluate --split test` rồi `audit-templates`.")

with tab_db:
    st.markdown("Chỉ đọc. Mỗi chiến lược là một bảng riêng trong PostgreSQL + pgvector.")
    st.dataframe(pd.DataFrame({"bảng": [f"chunks_{c.lower()}" for c in STRATEGIES],
                               "chiến lược": [STRATEGIES[c].name for c in STRATEGIES],
                               "số chunk": [counts[c] for c in STRATEGIES]}), hide_index=True)
    db_code = st.selectbox("Xem mẫu bảng", list(STRATEGIES), key="db_strategy")
    st.code(f"SELECT chunk_id, version, page_start, page_end, dieu, left(text, 80)\nFROM chunks_{db_code.lower()}\n"
            "ORDER BY chunk_id LIMIT 20;", language="sql")
    rows = store.sample_rows(db_code, limit=20)
    if rows:
        st.dataframe(pd.DataFrame(rows).assign(text=lambda d: d["text"].str.slice(0, 80)), hide_index=True)
    st.markdown("**Kết nối bằng DBeaver:** host `127.0.0.1` · port `55433` · database `day6_lab` · user `day6` · "
                "mật khẩu: xem `starter/.env` (biến `DATABASE_URL`).")
