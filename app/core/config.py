"""
Configuration loading for Jarvis v2 Core.

Configuration is stored in a simple JSON file:
    config/settings.json

This module provides a small helper to load it as a Python dictionary.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from dotenv import load_dotenv
from pathlib import Path
from typing import Any, Dict, List, Optional

from .utils import get_project_root, ensure_directory

load_dotenv()


CONFIG_RELATIVE_PATH = Path("config") / "settings.json"


@dataclass
class TelegramConfig:
    """Settings related to Telegram API access."""

    api_id: int
    api_hash: str
    session_name: str
    channels: List[str]


@dataclass
class AIConfig:
    """Top-level AI provider selection."""

    provider: str = "cloud"


@dataclass
class DeliveryConfig:
    """Optional delivery settings (where Jarvis publishes digests)."""

    telegram_target: str = ""


@dataclass
class DebugConfig:
    """Debug and testing configuration options."""

    reuse_analyzed_messages: bool = False


@dataclass
class OpportunityConfig:
    """Opportunity hunter configuration."""

    enabled: bool = True
    backfill_batch_size: int = 200
    max_age_days: int = 90
    report_top_n: int = 8
    publish_to_telegram: bool = True
    min_score: int = 6


@dataclass
class JarvisConfig:
    """Top-level configuration structure for Jarvis v2."""

    telegram: TelegramConfig
    ai: AIConfig
    delivery: DeliveryConfig
    debug: DebugConfig
    opportunity: OpportunityConfig
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

    env_api_id = os.getenv("TELEGRAM_API_ID", "").strip()
    env_api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()

    if env_api_id or env_api_hash:
        if not env_api_id or not env_api_hash:
            raise ValueError(
                "Both TELEGRAM_API_ID and TELEGRAM_API_HASH must be set if either is present in the environment."
            )
        try:
            telegram_api_id = int(env_api_id)
        except ValueError as exc:
            raise ValueError("TELEGRAM_API_ID must be an integer.") from exc
        telegram_api_hash = env_api_hash
    else:
        telegram_api_id = int(raw.get("telegram", {}).get("api_id", 0))
        telegram_api_hash = str(raw.get("telegram", {}).get("api_hash", ""))

    if telegram_api_id <= 0 or not telegram_api_hash:
        raise ValueError(
            "Telegram API credentials are not configured. "
            "Set TELEGRAM_API_ID and TELEGRAM_API_HASH in .env or add them to config/settings.json."
        )

    telegram_cfg = TelegramConfig(
        api_id=telegram_api_id,
        api_hash=telegram_api_hash,
        session_name=str(raw.get("telegram", {}).get("session_name", "jarvis_session")),
        channels=list(raw.get("telegram", {}).get("channels", [])),
    )

    ai_cfg = AIConfig(
        provider=str(raw.get("ai", {}).get("provider", AIConfig().provider)),
    )

    delivery_cfg = DeliveryConfig(
        telegram_target=str(raw.get("delivery", {}).get("telegram_target", "")),
    )

    debug_cfg = DebugConfig(
        reuse_analyzed_messages=bool(raw.get("debug", {}).get("reuse_analyzed_messages", False)),
    )

    opportunity_cfg = OpportunityConfig(
        enabled=bool(raw.get("opportunity", {}).get("enabled", OpportunityConfig().enabled)),
        backfill_batch_size=max(10, int(raw.get("opportunity", {}).get("backfill_batch_size", OpportunityConfig().backfill_batch_size))),
        max_age_days=max(7, int(raw.get("opportunity", {}).get("max_age_days", OpportunityConfig().max_age_days))),
        report_top_n=max(3, int(raw.get("opportunity", {}).get("report_top_n", OpportunityConfig().report_top_n))),
        publish_to_telegram=bool(raw.get("opportunity", {}).get("publish_to_telegram", OpportunityConfig().publish_to_telegram)),
        min_score=max(1, min(10, int(raw.get("opportunity", {}).get("min_score", OpportunityConfig().min_score)))),
    )

    try:
        digest_max_age_days = int(raw.get("digest_max_age_days", 3))
    except (TypeError, ValueError):
        digest_max_age_days = 3
    digest_max_age_days = max(1, digest_max_age_days)

    _cached_config = JarvisConfig(
        telegram=telegram_cfg,
        ai=ai_cfg,
        delivery=delivery_cfg,
        debug=debug_cfg,
        opportunity=opportunity_cfg,
        database_path=db_path,
        log_level=str(raw.get("logging", {}).get("level", "INFO")),
        digest_max_age_days=digest_max_age_days,
    )
    return _cached_config

