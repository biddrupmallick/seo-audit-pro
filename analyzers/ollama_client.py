"""
Central Ollama client. Reads OLLAMA_HOST and OLLAMA_MODEL from config.
Uses the ollama Python library with configurable host (supports local + ngrok/remote).
"""
from typing import Optional
import ollama as _ollama

from config import OLLAMA_HOST, OLLAMA_MODEL

# ngrok requires this header to skip the browser warning interstitial
_EXTRA_HEADERS = {"ngrok-skip-browser-warning": "true"}

# Single client instance pointing to configured host
_client = _ollama.Client(host=OLLAMA_HOST, headers=_EXTRA_HEADERS)


def ask(prompt: str, max_tokens: int = 500, temperature: float = 0.7, model: Optional[str] = None) -> str:
    """Send a prompt to Ollama and return the response text."""
    _model = model or OLLAMA_MODEL
    try:
        response = _client.generate(
            model=_model,
            prompt=prompt,
            options={"temperature": temperature, "num_predict": max_tokens},
        )
        return response["response"].strip()
    except Exception as e:
        print(f"Ollama error ({OLLAMA_HOST}): {e}")
        return ""


def chat(messages: list, max_tokens: int = 500, temperature: float = 0.7, model: Optional[str] = None) -> str:
    """Send a chat message list to Ollama and return the assistant response text."""
    _model = model or OLLAMA_MODEL
    try:
        response = _client.chat(
            model=_model,
            messages=messages,
            options={"temperature": temperature, "num_predict": max_tokens},
        )
        return response["message"]["content"].strip()
    except Exception as e:
        print(f"Ollama chat error ({OLLAMA_HOST}): {e}")
        return ""
