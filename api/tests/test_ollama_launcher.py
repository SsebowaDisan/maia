from __future__ import annotations

from api.services.ollama.launcher import quickstart_payload


def test_quickstart_payload_contains_required_commands() -> None:
    payload = quickstart_payload(base_url="http://127.0.0.1:11434")

    assert payload["base_url"] == "http://127.0.0.1:11434"
    assert payload["install_url"]
    commands = payload["commands"]
    assert commands["check"] == "ollama --version"
    assert commands["start"] == "ollama serve"
    assert "ollama pull" in commands["pull_model"]
    assert "ollama pull" in commands["pull_embedding"]
