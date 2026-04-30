from __future__ import annotations

import os
from typing import Any, Dict, Optional

import requests

from ..core.config import get_config
from ..core.logger import get_logger
from .base_client import BaseAIClient

logger = get_logger(__name__)


class OpenAIClient(BaseAIClient):
    def __init__(self) -> None:
        cfg = get_config().openai
        self.base_url = cfg.base_url.rstrip("/")
        self.model = cfg.model
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()

    def generate(self, prompt: str, timeout: int = 60) -> Optional[str]:
        if not self.api_key:
            logger.error("Missing/invalid OPENAI_API_KEY; OpenAI call skipped.")
            return None

        url = f"{self.base_url}/chat/completions"
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": 2048,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        if "openrouter.ai" in self.base_url:
            site_url = os.getenv("OPENROUTER_SITE_URL", "").strip()
            app_name = os.getenv("OPENROUTER_APP_NAME", "").strip()
            if site_url:
                headers["HTTP-Referer"] = site_url
            if app_name:
                headers["X-OpenRouter-Title"] = app_name

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
            if not (200 <= resp.status_code < 300):
                # Helpful debugging for OpenAI-compatible endpoints (OpenRouter included).
                logger.error(
                    "OpenAI HTTP error (non-2xx): status=%s model=%s base_url=%s response=%r",
                    resp.status_code,
                    self.model,
                    self.base_url,
                    resp.text,
                )
                return None
            data = resp.json()
        except requests.RequestException as exc:  # noqa: BLE001
            logger.error("OpenAI HTTP request failed: %s", exc)
            return None
        except ValueError as exc:  # JSON decoding
            logger.error("OpenAI response JSON decode failed: %s", exc)
            return None

        try:
            content = data["choices"][0]["message"]["content"]
            if isinstance(content, str):
                return content.strip() or None
        except (KeyError, IndexError, TypeError):  # noqa: PERF203
            logger.error("Unexpected OpenAI response format: %r", data)
            return None

        return None

