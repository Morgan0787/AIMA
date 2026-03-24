from __future__ import annotations

import os
from typing import Optional

from ..core.config import get_config
from ..core.logger import get_logger
from .base_client import BaseAIClient

logger = get_logger(__name__)

try:
    # Official Google GenAI SDK.
    from google import genai  # type: ignore
except Exception:  # pragma: no cover
    genai = None


class GeminiClient(BaseAIClient):
    def __init__(self) -> None:
        cfg = get_config().gemini
        self.model = cfg.model
        self.api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self._client = None

        if not self.api_key:
            return

        if genai is None:
            logger.error("google-genai SDK is not available; cannot call Gemini.")
            return

        try:
            self._client = genai.Client(api_key=self.api_key)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to initialize Gemini client: %s", exc)
            self._client = None

    def generate(self, prompt: str, timeout: int = 60) -> str | None:
        if not self.api_key or self._client is None:
            logger.error("Missing/invalid GEMINI_API_KEY; Gemini call skipped.")
            return None

        try:
            # Send plain text prompt; SDK returns a response with `.text`.
            resp = self._client.models.generate_content(model=self.model, contents=prompt)
            text = getattr(resp, "text", None)
            if isinstance(text, str):
                return text.strip() or None
            return None
        except Exception as exc:  # noqa: BLE001
            logger.exception("Gemini generation failed: %s", exc)
            return None

