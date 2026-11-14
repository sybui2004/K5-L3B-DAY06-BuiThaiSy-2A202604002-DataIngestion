"""Shared, cached resources of the demo app (store, embedder, parsed corpus, benchmark questions)."""
from dataclasses import dataclass, field

from .. import config
from ..benchmark import load_questions
from .health import check_services


@dataclass
class Services:
    store: object | None
    embedder: object | None
    pages_by_doc: dict = field(default_factory=dict)
    health: dict = field(default_factory=dict)
    questions: list = field(default_factory=list)


def build_services() -> Services:
    health = check_services(config.DATABASE_URL, config.OLLAMA_URL, config.EMBED_MODEL)
    if any(health.values()):
        return Services(None, None, health=health)
    from ..embeddings import OllamaEmbedder
    from ..run import load_corpus
    from ..store import PgVectorStore
    embedder = OllamaEmbedder()
    return Services(PgVectorStore(config.DATABASE_URL, embedder.dimensions), embedder, load_corpus(), health,
                    load_questions(config.BENCHMARK_PATH))


def get_services() -> Services:
    import streamlit as st

    @st.cache_resource(show_spinner="Đang khởi động dịch vụ…")
    def _cached() -> Services:
        return build_services()

    svc = _cached()
    if any(svc.health.values()):  # never keep a failed start in the cache: retry on the next load
        _cached.clear()
    return svc
