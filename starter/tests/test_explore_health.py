import pytest

from src import config
from src.explore.health import check_services


def test_unreachable_hosts_return_messages_not_exceptions():
    res = check_services("postgresql://u:p@127.0.0.1:1/x", "http://127.0.0.1:1", "bge-m3")
    assert "docker compose up -d" in res["postgres"]
    assert "ollama" in res["ollama"].lower()


@pytest.mark.db
@pytest.mark.ollama
def test_real_services_healthy():
    assert check_services(config.DATABASE_URL, config.OLLAMA_URL, config.EMBED_MODEL) == {"postgres": None, "ollama": None}


def test_missing_model_reported(monkeypatch):
    import src.explore.health as h
    monkeypatch.setattr(h, "_ollama_models", lambda url: ["other-model:latest"])
    res = check_services("postgresql://u:p@127.0.0.1:1/x", "http://x", "bge-m3")
    assert "ollama pull bge-m3" in res["ollama"]
