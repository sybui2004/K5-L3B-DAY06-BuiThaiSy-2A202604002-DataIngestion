import math

import pytest

from src.embeddings import EmbeddingBackendError, OllamaEmbedder


def _cos(a, b):
    return sum(x * y for x, y in zip(a, b)) / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


def test_unreachable_backend_raises():
    with pytest.raises(EmbeddingBackendError) as exc:
        OllamaEmbedder(base_url="http://127.0.0.1:9")
    msg = str(exc.value).lower()
    assert "ollama" in msg and "bge-m3" in msg


@pytest.mark.ollama
def test_missing_model_raises():
    with pytest.raises(EmbeddingBackendError):
        OllamaEmbedder(model_name="no-such-model-xyz")


@pytest.mark.ollama
def test_real_dimensions_and_similarity():
    e = OllamaEmbedder()
    assert e.dimensions == 1024
    q = e.embed_query("thời giờ làm thêm")
    near, far = e.embed_documents(["làm thêm giờ", "trả lương bằng tiền đồng"])
    assert _cos(q, near) > _cos(q, far)
    info = e.info()
    assert info["model"] == "bge-m3" and info["dimensions"] == 1024 and info["ollama_version"]


@pytest.mark.ollama
def test_batch_order_preserved():
    e = OllamaEmbedder(batch_size=16)
    texts = [f"Điều {i} quy định về lao động số {i}" for i in range(20)]
    batched = e.embed_documents(texts)
    for i in (0, 7, 19):
        single = e.embed_documents([texts[i]])[0]
        assert max(abs(a - b) for a, b in zip(batched[i], single)) < 1e-3
