from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

from openai import (
    APIConnectionError,
    APIError,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
)

from ..core.logger import get_logger
from .base_client import BaseAIClient

logger = get_logger(__name__)

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_MODEL = "llama-3.1-8b-instant"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = "meta-llama/llama-3-8b-instruct"

_KEY_COOLDOWN_SECONDS = 60.0


class Provider(str, Enum):
    GROQ = "groq"
    OPENROUTER = "openrouter"


@dataclass
class APIKeySlot:
    provider: Provider
    api_key: str
    inactive_until: float = 0.0

    def mark_inactive(self, cooldown_seconds: float = _KEY_COOLDOWN_SECONDS) -> None:
        self.inactive_until = time.time() + cooldown_seconds

    def is_active(self) -> bool:
        return time.time() >= self.inactive_until

    @property
    def label(self) -> str:
        return f"{self.provider.value}:{self.api_key[:8]}..."


def _parse_api_keys(env_var: str) -> List[str]:
    raw = os.getenv(env_var, "").strip()
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def _build_key_pool() -> List[APIKeySlot]:
    slots: List[APIKeySlot] = []
    for key in _parse_api_keys("GROQ_API_KEYS"):
        slots.append(APIKeySlot(provider=Provider.GROQ, api_key=key))
    for key in _parse_api_keys("OPENROUTER_API_KEYS"):
        slots.append(APIKeySlot(provider=Provider.OPENROUTER, api_key=key))
    return slots


class AIClient(BaseAIClient):
    """
    Fault-tolerant OpenAI-compatible client with Groq + OpenRouter key pools.

    Keys rotate round-robin (all Groq keys first, then OpenRouter, then repeat).
    Failed keys are temporarily skipped on rate-limit or auth errors.
    """

    @property
    def pool_size(self) -> int:
        """Number of configured API key slots in the rotation pool."""
        return len(self._slots)

    def __init__(self) -> None:
        self._slots = _build_key_pool()
        self._index = 0
        self._lock = threading.Lock()
        self._clients: Dict[str, OpenAI] = {}

        if not self._slots:
            logger.error(
                "No API keys configured. Set GROQ_API_KEYS and/or OPENROUTER_API_KEYS."
            )
        else:
            groq_count = sum(1 for slot in self._slots if slot.provider == Provider.GROQ)
            openrouter_count = len(self._slots) - groq_count
            logger.info(
                "AI key pool ready: groq=%d openrouter=%d total=%d",
                groq_count,
                openrouter_count,
                len(self._slots),
            )

    def _next_active_slot(self) -> Optional[APIKeySlot]:
        if not self._slots:
            return None

        with self._lock:
            for _ in range(len(self._slots)):
                slot = self._slots[self._index]
                self._index = (self._index + 1) % len(self._slots)
                if slot.is_active():
                    return slot
        return None

    def _model_for(self, slot: APIKeySlot) -> str:
        if slot.provider == Provider.GROQ:
            return GROQ_MODEL
        return OPENROUTER_MODEL

    def _base_url_for(self, slot: APIKeySlot) -> str:
        if slot.provider == Provider.GROQ:
            return GROQ_BASE_URL
        return OPENROUTER_BASE_URL

    def _get_client(self, slot: APIKeySlot) -> OpenAI:
        cache_key = f"{slot.provider.value}:{slot.api_key}"
        with self._lock:
            cached = self._clients.get(cache_key)
            if cached is not None:
                return cached

            default_headers: Dict[str, str] = {}
            if slot.provider == Provider.OPENROUTER:
                site_url = os.getenv("OPENROUTER_SITE_URL", "").strip()
                app_name = os.getenv("OPENROUTER_APP_NAME", "").strip()
                if site_url:
                    default_headers["HTTP-Referer"] = site_url
                if app_name:
                    default_headers["X-OpenRouter-Title"] = app_name

            client = OpenAI(
                api_key=slot.api_key,
                base_url=self._base_url_for(slot),
                default_headers=default_headers or None,
            )
            self._clients[cache_key] = client
            return client

    @staticmethod
    def _is_key_error(exc: Exception) -> bool:
        if isinstance(
            exc,
            (
                RateLimitError,
                AuthenticationError,
                PermissionDeniedError,
                BadRequestError,
                NotFoundError,
            ),
        ):
            return True
        if isinstance(exc, APIConnectionError):
            return True
        if isinstance(exc, APIError):
            status_code = getattr(exc, "status_code", None)
            if status_code in {400, 401, 403, 404, 429, 500, 502, 503}:
                return True
        err_text = str(exc).lower()
        return any(
            token in err_text
            for token in (
                "400",
                "404",
                "429",
                "rate limit",
                "too many requests",
                "unauthorized",
                "authentication",
                "invalid api key",
                "permission denied",
                "not found",
                "decommissioned",
                "model_decommissioned",
            )
        )

    def generate(self, prompt: str, timeout: int = 60) -> str | None:
        if not self._slots:
            return None

        attempts_left = len(self._slots)
        while attempts_left > 0:
            slot = self._next_active_slot()
            if slot is None:
                logger.error("All API keys are temporarily inactive.")
                return None

            attempts_left -= 1
            client = self._get_client(slot)
            model = self._model_for(slot)

            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    max_tokens=2048,
                    timeout=timeout,
                )
                content = response.choices[0].message.content
                if isinstance(content, str):
                    return content.strip() or None
                return None
            except Exception as exc:  # noqa: BLE001
                if self._is_key_error(exc):
                    logger.warning(
                        "API key error for %s (model=%s): %s. Rotating to next key.",
                        slot.label,
                        model,
                        exc,
                    )
                    slot.mark_inactive()
                    continue
                logger.exception("Non-retryable AI generation error for %s: %s", slot.label, exc)
                return None

        logger.error("All API keys failed for the current request.")
        return None
