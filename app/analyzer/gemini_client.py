from __future__ import annotations

import os
import time
from typing import Optional

from ..core.config import get_config
from ..core.logger import get_logger
from .base_client import BaseAIClient

logger = get_logger(__name__)

try:
    # Official Google Generative AI SDK.
    import google.generativeai as genai  # type: ignore
    from google.api_core.exceptions import ResourceExhausted  # type: ignore
except Exception:  # pragma: no cover
    genai = None
    ResourceExhausted = Exception  # type: ignore


class GeminiClient(BaseAIClient):
    def __init__(self) -> None:
        cfg = get_config().gemini
        configured_model = str(cfg.model or "").strip()
        if configured_model and not configured_model.startswith("models/"):
            configured_model = f"models/{configured_model}"
        self.model = configured_model or "models/gemini-1.5-flash"
        self.api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self._client = None

        if not self.api_key:
            return

        if genai is None:
            logger.error("google-generativeai SDK is not available; cannot call Gemini.")
            return

        try:
            genai.configure(api_key=self.api_key)
            self._client = genai.GenerativeModel(self.model)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to initialize Gemini client: %s", exc)
            self._client = None

    def generate(self, prompt: str, timeout: int = 60) -> str | None:
        if not self.api_key or self._client is None:
            logger.error("Missing/invalid GEMINI_API_KEY; Gemini call skipped.")
            return None

        for attempt in range(2):
            try:
                resp = self._client.generate_content(prompt)
                text = getattr(resp, "text", None)
                if isinstance(text, str):
                    return text.strip() or None
                return None
            except ResourceExhausted as exc:
                if attempt == 0:
                    logger.warning(
                        "Gemini rate limit hit (429/ResourceExhausted). Waiting 10s before retry..."
                    )
                    time.sleep(10)
                    continue
                logger.exception("Gemini generation failed after retry: %s", exc)
                return None
            except Exception as exc:  # noqa: BLE001
                err_text = str(exc).lower()
                if attempt == 0 and ("429" in err_text or "resource_exhausted" in err_text):
                    logger.warning(
                        "Gemini returned 429-style error. Waiting 10s before retry..."
                    )
                    time.sleep(10)
                    continue
                logger.exception("Gemini generation failed: %s", exc)
                return None
        return None

