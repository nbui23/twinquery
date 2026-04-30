import pytest
import requests

from twinquery.llm.ollama_client import OllamaError, generate


class FakeResponse:
    status_code = 404
    text = '{"error":"model qwen2.5:7b not found"}'

    def raise_for_status(self) -> None:
        raise AssertionError("404 branch should handle before raise_for_status")


def test_generate_404_includes_model_hint(monkeypatch) -> None:
    def fake_post(*args, **kwargs) -> FakeResponse:
        return FakeResponse()

    monkeypatch.setattr(requests, "post", fake_post)
    with pytest.raises(OllamaError) as exc_info:
        generate("SELECT 1")

    message = str(exc_info.value)
    assert "ollama pull" in message.lower()
    assert "qwen2.5:7b" in message
    assert "model qwen2.5:7b not found" in message
