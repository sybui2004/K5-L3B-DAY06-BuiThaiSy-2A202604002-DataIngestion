"""Paths and constants fixed by the design spec (docs/superpowers/specs/...-design.md)."""
import os
from pathlib import Path

from dotenv import load_dotenv

STARTER_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = STARTER_DIR.parent
load_dotenv(STARTER_DIR / ".env")

DATA_RAW = REPO_ROOT / "data" / "raw"
MANIFEST_PATH = REPO_ROOT / "data" / "manifest.csv"
BENCHMARK_PATH = REPO_ROOT / "benchmark" / "questions.jsonl"
RESULTS_DIR = REPO_ROOT / "results"
EXPERIMENT_LOG = REPO_ROOT / "artifacts" / "experiment_log.csv"

DOCUMENTS = [
    {
        "document_id": "blld-2012",
        "filename": "blld_2012_congbao.pdf",
        "version": "2012",
        "title": "Bộ luật Lao động số 10/2012/QH13",
        "source_url": "https://congbao.chinhphu.vn/van-ban/luat-so-10-2012-qh13-2771.htm",
        "gazette_issue": "Công báo số 475+476, ngày 05-8-2012",
    },
    {
        "document_id": "blld-2019",
        "filename": "blld_2019_congbao.pdf",
        "version": "2019",
        "title": "Bộ luật Lao động số 45/2019/QH14",
        "source_url": "https://congbaocdn.chinhphu.vn/CongBaoCP/VanBan/2019/11/30232/29070-1-2019993-99445-2019-qh14.pdf",
        "gazette_issue": "Công báo số 993+994, ngày 26-12-2019",
    },
]

EMBED_MODEL = "bge-m3"
EMBED_DIM = 1024
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
DATABASE_URL = os.getenv("DATABASE_URL", "")

A_SIZE = 800
A_OVERLAP = 100
B_MAX = 1500
MIN_PAGE_CHARS = 200
MIN_EVIDENCE_CHARS = 30
TOP_K = 3
COHERENCE_PAGES = (5, 15, 25, 35, 45)

# Exploration strategies (D/E/F) — not part of the frozen A/B/C submission
D_SIZE = 800
D_OVERLAP = 100
E_SIM_THRESHOLD = 0.4  # tuned on blld-2019 pages 21-36: adjacent-sentence cosine p15 = 0.40, median 0.505
E_MIN = 200  # do not cut while the current chunk is shorter than this
E_MAX = 1500
F_CHILD_SIZE = 300
EXPLORE_DIR = RESULTS_DIR / "explore"
