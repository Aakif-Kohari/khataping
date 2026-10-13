"""Tiny client for a local Ollama server running an open-weight Gemma model."""
from __future__ import annotations

import os

import requests

DEFAULT_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = os.getenv("KHATAPING_MODEL", "gemma3:4b")


class LLMUnavailable(RuntimeError):
    """The local model server could not be reached or returned nothing."""


def ollama_available(url: str = DEFAULT_URL, timeout: float = 1.5) -> bool:
    try:
        return requests.get(f"{url}/api/tags", timeout=timeout).ok
    except requests.RequestException:
        return False


def generate(prompt: str, model: str = DEFAULT_MODEL, url: str = DEFAULT_URL,
             timeout: float = 90.0) -> str:
    """Run one non-streaming generation against the local model."""
    try:
        resp = requests.post(
            f"{url}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.4, "num_predict": 220},
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        text = (resp.json().get("response") or "").strip()
    except (requests.RequestException, ValueError) as exc:
        raise LLMUnavailable(str(exc)) from exc
    if not text:
        raise LLMUnavailable("The model returned an empty response.")
    return text
