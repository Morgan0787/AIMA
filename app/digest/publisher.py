"""
Digest publishing utilities for Jarvis v2 Core.

This module will handle publishing the daily digest, for example:
- Printing to the console
- Saving to a file
- (Later) sending via Telegram or email
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from telethon import TelegramClient

from ..core.config import get_config
from ..core.logger import get_logger
from ..core.utils import get_project_root, ensure_directory


logger = get_logger(__name__)


def publish_to_console(digest_text: str) -> None:
    """
    Print the digest to the console.
    """
    logger.info("Publishing digest to console.")
    print("\n=== Jarvis Daily Digest ===\n")
    print(digest_text)
    print("\n===========================\n")


def save_to_file(digest_text: str, filename: str | None = None) -> Path:
    """
    Save the digest to a text file under `data/digests`.

    If no filename is given, a name based on the current date is used.
    """
    project_root = get_project_root()
    digests_dir = project_root / "data" / "digests"
    ensure_directory(digests_dir)

    if filename is None:
        today = datetime.utcnow().date().isoformat()
        filename = f"digest_{today}.txt"

    path = digests_dir / filename
    path.write_text(digest_text, encoding="utf-8")
    logger.info("Saved digest to %s", path)
    return path


def publish_digest(digest_text: str, title: str | None = None) -> Tuple[bool, Optional[str]]:
    """
    Publish a digest using the configured delivery method.

    Behavior:
    - If `delivery.telegram_target` is configured, send to Telegram.
    - Otherwise, save locally and print to console.

    Returns:
        (published, published_to)
    """
    config = get_config()
    target = (config.delivery.telegram_target or "").strip()

    # Always save locally for reliability/audit.
    filename = None
    if title:
        safe = "".join(ch for ch in title if ch.isalnum() or ch in {" ", "-", "_"}).strip()
        safe = safe.replace(" ", "_")[:60]
        if safe:
            filename = f"{safe}.txt"
    save_to_file(digest_text, filename=filename)

    if not target:
        logger.info("No Telegram target configured in delivery.telegram_target")
        publish_to_console(digest_text)
        return False, None

    logger.info("Attempting to publish digest to Telegram target: %s", target)

    # Small retry for better delivery reliability in production-like runs.
    max_attempts = 2
    for attempt in range(1, max_attempts + 1):
        try:
            asyncio.run(_send_to_telegram(digest_text, target))
            logger.info(
                "Successfully published digest to Telegram target: %s (attempt %d/%d)",
                target,
                attempt,
                max_attempts,
            )
            return True, target
        except ValueError as exc:
            # Entity resolution errors - don't retry, these are configuration issues
            logger.error(
                "Failed to resolve Telegram target '%s': %s. Please check the target configuration.",
                target,
                exc,
            )
            break
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Failed to publish digest to Telegram (%s), attempt %d/%d: %s",
                target,
                attempt,
                max_attempts,
                exc,
            )
            if attempt < max_attempts:
                time.sleep(1.5)

    # Fallback: still print to console so the user sees it.
    logger.warning("Telegram publishing failed, falling back to console output")
    publish_to_console(digest_text)
    return False, None


async def _send_to_telegram(digest_text: str, target: str) -> None:
    """
    Send the digest to a Telegram chat/channel using Telethon.

    Note:
    Telegram has message length limits. We split long digests into chunks.
    """
    cfg = get_config().telegram

    project_root = get_project_root()
    session_dir = ensure_directory(project_root / "data" / "session")
    session_path = session_dir / cfg.session_name

    client = TelegramClient(str(session_path), cfg.api_id, cfg.api_hash)

    async with client:
        await client.start()
        
        # Resolve target entity
        entity = await _resolve_target_entity(client, target)
        if entity is None:
            raise ValueError(f"Could not resolve Telegram target: {target}")
        
        logger.info("Sending digest to Telegram entity: %s (ID: %s)", 
                   getattr(entity, 'title', getattr(entity, 'username', str(entity.id))),
                   entity.id)

        # Telegram typical max length is 4096 chars; keep a safe margin.
        chunks = _split_text(digest_text, max_len=3500)
        for idx, chunk in enumerate(chunks):
            await client.send_message(entity, chunk)
        
        logger.info("Successfully sent digest with %d chunk(s) to %s", len(chunks), target)


async def _resolve_target_entity(client: TelegramClient, target: str):
    """
    Resolve Telegram target to entity using multiple methods.
    
    Supports:
    - @username format
    - numeric chat ID
    - chat title (partial match)
    """
    if not target or not target.strip():
        logger.error("Empty Telegram target provided")
        return None
    
    target = target.strip()
    logger.info("Resolving Telegram target: %s", target)
    
    # Try direct entity resolution first (handles @username and numeric IDs)
    try:
        entity = await client.get_entity(target)
        logger.info("Resolved target directly: %s", target)
        return entity
    except Exception as e:
        logger.debug("Could not resolve target directly: %s", e)
    
    # Try as numeric ID if target looks like a number
    if target.lstrip('-').isdigit():
        try:
            entity = await client.get_entity(int(target))
            logger.info("Resolved target as numeric ID: %s", target)
            return entity
        except Exception as e:
            logger.debug("Could not resolve target as numeric ID: %s", e)
    
    # Try to find by title match
    try:
        async for dialog in client.iter_dialogs():
            if hasattr(dialog.entity, 'title') and dialog.entity.title:
                if target.lower() in dialog.entity.title.lower():
                    logger.info("Resolved target by title match: %s -> %s", 
                              target, dialog.entity.title)
                    return dialog.entity
            elif hasattr(dialog.entity, 'username') and dialog.entity.username:
                if target.lstrip('@').lower() == dialog.entity.username.lower():
                    logger.info("Resolved target by username match: %s -> %s", 
                              target, dialog.entity.username)
                    return dialog.entity
    except Exception as e:
        logger.error("Error searching dialogs: %s", e)
    
    logger.error("Could not resolve Telegram target: %s", target)
    return None


async def list_available_dialogs():
    """
    Optional utility to list available Telegram dialogs for user reference.
    """
    cfg = get_config().telegram
    project_root = get_project_root()
    session_dir = ensure_directory(project_root / "data" / "session")
    session_path = session_dir / cfg.session_name

    client = TelegramClient(str(session_path), cfg.api_id, cfg.api_hash)

    async with client:
        await client.start()
        
        print("\n=== Available Telegram Dialogs ===")
        async for dialog in client.iter_dialogs():
            name_parts = []
            if hasattr(dialog.entity, 'title') and dialog.entity.title:
                name_parts.append(f"Title: {dialog.entity.title}")
            if hasattr(dialog.entity, 'username') and dialog.entity.username:
                name_parts.append(f"@{dialog.entity.username}")
            name_parts.append(f"ID: {dialog.entity.id}")
            
            print(" | ".join(name_parts))
        print("================================\n")


def _split_text(text: str, max_len: int) -> list[str]:
    """
    Split long text into chunks not exceeding max_len, preferring paragraph breaks.
    """
    text = text.strip()
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= max_len:
            chunks.append(remaining)
            break

        cut = remaining[:max_len]
        # Prefer splitting on double newline.
        split_at = cut.rfind("\n\n")
        if split_at < int(max_len * 0.5):
            split_at = cut.rfind("\n")
        if split_at < int(max_len * 0.5):
            split_at = max_len

        chunk = remaining[:split_at].strip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[split_at:].lstrip()

    return chunks

