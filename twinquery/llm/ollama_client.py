"""Local Ollama client."""

from __future__ import annotations

from twinquery.config import get_settings


class OllamaError(RuntimeError):
    """Raised when local Ollama generation fails."""


def generate(prompt: str, timeout: int = 60) -> str:
    """Generate text with local Ollama."""
    try:
        import requests
    except ImportError as exc:
        raise OllamaError("requests is required for Ollama calls. Install dependencies first.") from exc

    settings = get_settings()
    model = settings.ollama_model or "qwen2.5:7b"
    payload = {"model": model, "prompt": prompt, "stream": False}

    try:
        response = requests.post(
            f"{settings.ollama_base_url.rstrip('/')}/api/generate",
            json=payload,
            timeout=timeout,
        )
        if response.status_code == 404:
            detail = response.text.strip()
            raise OllamaError(
                "Ollama returned 404. This usually means the configured model is not pulled "
                f"or OLLAMA_BASE_URL is not an Ollama server. Model: `{model}`. "
                f"Run `ollama pull {model}`. Response: {detail}"
            )
        response.raise_for_status()
    except requests.exceptions.ConnectionError as exc:
        raise OllamaError(
            "Ollama is not running or is unreachable. Start it with `ollama serve` "
            f"and pull the configured model with `ollama pull {model}`."
        ) from exc
    except requests.exceptions.Timeout as exc:
        raise OllamaError(f"Ollama request timed out after {timeout} seconds.") from exc
    except requests.RequestException as exc:
        response = getattr(exc, "response", None)
        detail = ""
        if response is not None and getattr(response, "text", ""):
            detail = f" Response: {response.text.strip()}"
        raise OllamaError(f"Ollama request failed: {exc}.{detail}") from exc

    data = response.json()
    text = str(data.get("response", "")).strip()
    if not text:
        raise OllamaError("Ollama returned an empty response.")
    return text
