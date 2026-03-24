"""
Configuration loading for Jarvis v2 Core.

Configuration is stored in a simple JSON file:
    config/settings.json

This module provides a small helper to load it as a Python dictionary.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .utils import get_project_root, ensure_directory


CONFIG_RELATIVE_PATH = Path("config") / "settings.json"


@dataclass
class TelegramConfig:
    """Settings related to Telegram API access."""

    api_id: int
    api_hash: str
    session_name: str
    channels: List[str]


@dataclass
class OllamaConfig:
    """Settings related to the local Ollama runtime."""

    base_url: str
    model: str


@dataclass
class AIConfig:
    """Top-level AI provider selection."""

    provider: str = "ollama"


@dataclass
class GeminiConfig:
    """Settings related to Google Gemini via the official GenAI SDK."""

    model: str = "gemini-2.0-flash"


@dataclass
class OpenAIConfig:
    """Settings related to OpenAI's chat completions API."""

    model: str = "gpt-4o-mini"
    base_url: str = "https://api.openai.com/v1"


@dataclass
class DeliveryConfig:
    """Optional delivery settings (where Jarvis publishes digests)."""

    telegram_target: str = ""


@dataclass
class DebugConfig:
    """Debug and testing configuration options."""

    reuse_analyzed_messages: bool = False


@dataclass
class JarvisConfig:
    """Top-level configuration structure for Jarvis v2."""

    telegram: TelegramConfig
    ollama: OllamaConfig
    ai: AIConfig
    gemini: GeminiConfig
    openai: OpenAIConfig
    delivery: DeliveryConfig
    debug: DebugConfig
    database_path: Path
    log_level: str = "INFO"
    digest_max_age_days: int = 3


_cached_config: Optional[JarvisConfig] = None


def _load_raw_config() -> Dict[str, Any]:
    """
    Load the raw JSON configuration from disk.

    If the file does not exist, a helpful error is raised telling the
    user to fill in `config/settings.json`.
    """
    project_root = get_project_root()
    config_path = project_root / CONFIG_RELATIVE_PATH

    if not config_path.exists():
        # Ensure the config directory exists and create a template if missing.
        ensure_directory(config_path.parent)
        raise FileNotFoundError(
            f"Configuration file not found at: {config_path}\n"
            "Please create this file based on the template and fill in your settings."
        )

    with config_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def get_config() -> JarvisConfig:
    """
    Load and cache the application configuration.

    Returns the same `JarvisConfig` instance on subsequent calls.
    """
    global _cached_config
    if _cached_config is not None:
        return _cached_config

    raw = _load_raw_config()
    project_root = get_project_root()

    db_path = project_root / raw.get("database", {}).get(
        "path", "data/jarvis.db"
    )

    telegram_cfg = TelegramConfig(
        api_id=int(raw.get("telegram", {}).get("api_id", 0)),
        api_hash=str(raw.get("telegram", {}).get("api_hash", "")),
        session_name=str(raw.get("telegram", {}).get("session_name", "jarvis_session")),
        channels=list(raw.get("telegram", {}).get("channels", [])),
    )

    ollama_cfg = OllamaConfig(
        base_url=str(raw.get("ollama", {}).get("base_url", "http://localhost:11434")),
        model=str(raw.get("ollama", {}).get("model", "gemma3:4b")),
    )

    ai_cfg = AIConfig(
        provider=str(raw.get("ai", {}).get("provider", AIConfig().provider)),
    )

    gemini_cfg = GeminiConfig(
        model=str(raw.get("gemini", {}).get("model", GeminiConfig().model)),
    )

    openai_cfg = OpenAIConfig(
        model=str(raw.get("openai", {}).get("model", OpenAIConfig().model)),
        base_url=str(raw.get("openai", {}).get("base_url", OpenAIConfig().base_url)),
    )

    delivery_cfg = DeliveryConfig(
        telegram_target=str(raw.get("delivery", {}).get("telegram_target", "")),
    )

    debug_cfg = DebugConfig(
        reuse_analyzed_messages=bool(raw.get("debug", {}).get("reuse_analyzed_messages", False)),
    )

    try:
        digest_max_age_days = int(raw.get("digest_max_age_days", 3))
    except (TypeError, ValueError):
        digest_max_age_days = 3
    digest_max_age_days = max(1, digest_max_age_days)

    _cached_config = JarvisConfig(
        telegram=telegram_cfg,
        ollama=ollama_cfg,
        ai=ai_cfg,
        gemini=gemini_cfg,
        openai=openai_cfg,
        delivery=delivery_cfg,
        debug=debug_cfg,
        database_path=db_path,
        log_level=str(raw.get("logging", {}).get("level", "INFO")),
        digest_max_age_days=digest_max_age_days,
    )
    return _cached_config

