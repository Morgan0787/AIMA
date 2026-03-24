"""
Minimal Ollama client for Jarvis v2 Core.

This module will send prompts to the local Ollama HTTP API and return
the model's responses.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import requests

from ..core.config import get_config
from ..core.logger import get_logger
from .base_client import BaseAIClient


logger = get_logger(__name__)


class OllamaClient(BaseAIClient):
    """
    Very small wrapper around the Ollama HTTP API.

    This keeps all Ollama-specific details in one place.
    """

    def __init__(self) -> None:
        cfg = get_config().ollama
        self.base_url = cfg.base_url.rstrip("/")
        self.model = cfg.model

    def generate(self, prompt: str, timeout: int = 180) -> Optional[str]:
        """
        Send a prompt to the Ollama model and return the generated text.

        Returns:
            The model's text response, or None if something went wrong.

        Notes:
            - Uses a simple blocking HTTP call.
            - Handles network errors and malformed JSON defensively.
        """
        url = f"{self.base_url}/api/generate"
        payload: Dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": "10m",
        }
        logger.info("Calling Ollama model '%s'...", self.model)

        try:
            response = requests.post(url, json=payload, timeout=timeout)
            response.raise_for_status()
        except requests.RequestException as exc:  # noqa: BLE001
            logger.error("Ollama HTTP error: %s", exc)
            return None

        # Ollama can stream or return multiple chunks; for simplicity we
        # support both a single-object and a basic streaming-style API.
        try:
            data = response.json()
        except ValueError as exc:  # JSONDecodeError is a subclass
            logger.error("Failed to decode Ollama JSON response: %s", exc)
            return None

        # If it's a single JSON object with a `response` field.
        if isinstance(data, dict) and "response" in data:
            return str(data.get("response", "")).strip() or None

        # If we ever get a list of chunks, try to join their `response` fields.
        if isinstance(data, list):
            parts = []
            for item in data:
                if isinstance(item, dict) and "response" in item:
                    parts.append(str(item["response"]))
            if parts:
                return "".join(parts).strip() or None

        logger.error("Unexpected Ollama response format: %r", data)
        return None

