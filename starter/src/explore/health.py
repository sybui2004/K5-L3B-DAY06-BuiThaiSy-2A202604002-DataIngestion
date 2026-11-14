"""Startup checks for the demo app: never raises, returns readable messages with the command to fix."""
import json
import urllib.request

import psycopg


def _ollama_models(base_url: str) -> list[str]:
    with urllib.request.urlopen(f"{base_url.rstrip('/')}/api/tags", timeout=3) as resp:
        return [m.get("name", "") for m in json.loads(resp.read().decode("utf-8")).get("models", [])]


def check_services(database_url: str, ollama_url: str, model: str) -> dict[str, str | None]:
    """{'postgres': None | message, 'ollama': None | message}; None means healthy."""
    result: dict[str, str | None] = {"postgres": None, "ollama": None}
    try:
        with psycopg.connect(database_url, connect_timeout=3) as conn:
            conn.execute("SELECT 1")
    except Exception as exc:  # noqa: BLE001 - any failure must become a message
        result["postgres"] = (f"Không kết nối được PostgreSQL ({type(exc).__name__}). "
                              "Chạy `docker compose up -d` trong thư mục starter/ rồi tải lại trang.")
    try:
        names = [n.split(":")[0] for n in _ollama_models(ollama_url)]
        if model not in names:
            result["ollama"] = f"Ollama chạy nhưng chưa có model {model}. Chạy `ollama pull {model}`."
    except Exception as exc:  # noqa: BLE001
        result["ollama"] = (f"Không kết nối được Ollama tại {ollama_url} ({type(exc).__name__}). "
                            f"Khởi động Ollama và chạy `ollama pull {model}`.")
    return result
