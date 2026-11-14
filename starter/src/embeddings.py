"""Real embedding provider: bge-m3 served by a local Ollama. Never falls back to mock vectors."""
import json
import urllib.error
import urllib.request
from typing import Protocol

from .config import EMBED_DIM, EMBED_MODEL, OLLAMA_URL


class Embedder(Protocol):
    model_name: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, question: str) -> list[float]: ...


class EmbeddingBackendError(RuntimeError):
    """Ollama is unreachable, the model is missing, or the response is unusable."""


class OllamaEmbedder:
    """Queries and documents are embedded identically (bge-m3 needs no prefixes)."""

    def __init__(self, model_name: str = EMBED_MODEL, base_url: str = OLLAMA_URL,
                 batch_size: int = 16, timeout: float = 120.0) -> None:
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")
        self.batch_size = batch_size
        self.timeout = timeout
        self.dimensions = len(self._embed(["kiểm tra"])[0])
        if model_name == EMBED_MODEL and self.dimensions != EMBED_DIM:
            raise EmbeddingBackendError(f"{model_name} returned {self.dimensions} dims, expected {EMBED_DIM}")

    def _request(self, path: str, payload: dict | None = None) -> dict:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(f"{self.base_url}{path}", data=data,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            raise EmbeddingBackendError(
                f"Ollama at {self.base_url} rejected model '{self.model_name}': {detail}. "
                f"Run `ollama pull {EMBED_MODEL}`.") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise EmbeddingBackendError(
                f"Cannot reach Ollama at {self.base_url} ({exc}). Start Ollama and run "
                f"`ollama pull {EMBED_MODEL}`; no mock fallback is used.") from exc

    def _embed(self, texts: list[str]) -> list[list[float]]:
        out = self._request("/api/embed", {"model": self.model_name, "input": texts}).get("embeddings")
        if not out or len(out) != len(texts):
            raise EmbeddingBackendError(f"Ollama returned {0 if not out else len(out)} vectors for {len(texts)} inputs")
        return out

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for i in range(0, len(texts), self.batch_size):
            vectors.extend(self._embed(texts[i:i + self.batch_size]))
        return vectors

    def embed_query(self, question: str) -> list[float]:
        return self._embed([question])[0]

    def info(self) -> dict:
        tags = self._request("/api/tags").get("models", [])
        digest = next((m.get("digest") for m in tags if m.get("name", "").split(":")[0] == self.model_name), None)
        return {"model": self.model_name, "dimensions": self.dimensions, "digest": digest,
                "ollama_version": self._request("/api/version").get("version"), "endpoint": f"{self.base_url}/api/embed"}
