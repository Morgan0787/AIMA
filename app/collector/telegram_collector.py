"""
Telegram collector for Jarvis v2 Core.

This module uses Telethon to:
- Connect to Telegram
- Iterate configured channels
- Fetch only messages newer than `channels.last_message_id`
- Save new messages into SQLite (`raw_messages`)

Beginner note:
Telethon is async, but we keep the app entrypoint (`main`) synchronous
by using `asyncio.run(...)` internally.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Tuple

from telethon import TelegramClient
from telethon.errors import RPCError
from telethon.tl.custom import Message

from ..core.config import get_config
from ..core.logger import get_logger
from ..core.utils import ensure_directory, get_project_root
from ..storage.repository import Repository


logger = get_logger(__name__)


def _normalize_channel_username(value: str) -> str:
    """
    Normalize a channel string into a usable username.

    Examples:
    - "@startupuz" -> "startupuz"
    - "https://t.me/startupuz" -> "startupuz"
    """
    value = value.strip()
    if value.startswith("https://t.me/"):
        value = value.replace("https://t.me/", "", 1)
    if value.startswith("http://t.me/"):
        value = value.replace("http://t.me/", "", 1)
    value = value.lstrip("@")
    value = value.split("/")[0]
    return value


def _build_post_link(username: Optional[str], message_id: int) -> Optional[str]:
    """
    Build a public t.me link for a message if the channel has a username.
    """
    if not username:
        return None
    clean = _normalize_channel_username(username)
    if not clean:
        return None
    return f"https://t.me/{clean}/{message_id}"


@dataclass
class CollectionResult:
    """Small result object returned by a collection run."""

    total_new_messages: int
    per_channel_counts: List[Tuple[str, int]]


class TelegramCollector:
    """
    Collects messages from Telegram channels.

    This collector is responsible only for collection into `raw_messages`.
    Processing, classification, and digest creation are Step 3+.
    """

    def __init__(self) -> None:
        self.config = get_config()
        self.repo = Repository()

        # Normalize channel entries now so we have consistent identifiers.
        self.channels: List[str] = [
            _normalize_channel_username(ch) for ch in self.config.telegram.channels
        ]

        # Store the Telethon session under `data/session/` so everything is local.
        project_root = get_project_root()
        session_dir = ensure_directory(project_root / "data" / "session")
        self.session_path = session_dir / self.config.telegram.session_name

    def collect_new_messages(self) -> CollectionResult:
        """
        Collect and store only new messages from all configured channels.

        Returns:
            CollectionResult with total count and per-channel counts.
        """
        return asyncio.run(self._collect_async())

    async def _collect_async(self) -> CollectionResult:
        """
        Async implementation using Telethon.
        """
        cfg = self.config.telegram
        client = TelegramClient(str(self.session_path), cfg.api_id, cfg.api_hash)

        per_channel_counts: List[Tuple[str, int]] = []
        total_new = 0

        logger.info("Connecting to Telegram...")
        async with client:
            # `start()` will prompt for login (phone/code) if no session exists yet.
            await client.start()

            for channel_username in self.channels:
                if not channel_username:
                    continue

                try:
                    channel = self.repo.get_or_create_channel(channel_username)
                    if channel.id is None:
                        raise RuntimeError("Channel record has no ID (unexpected).")
                    last_message_id = channel.last_message_id or 0

                    logger.info(
                        "Collecting from @%s (last_message_id=%s)...",
                        channel_username,
                        last_message_id,
                    )

                    entity = await client.get_entity(channel_username)

                    new_messages: List[Message] = []
                    # `min_id` returns messages with id > min_id.
                    async for msg in client.iter_messages(entity, min_id=last_message_id):
                        new_messages.append(msg)

                    # Telethon yields newest -> oldest; insert oldest -> newest.
                    new_messages.reverse()

                    inserted = 0
                    newest_seen = last_message_id
                    collected_at = datetime.utcnow()

                    for msg in new_messages:
                        if msg.id is None:
                            continue
                        if msg.id <= last_message_id:
                            continue

                        text = (msg.message or "").strip()
                        if not text:
                            # Skip empty text messages (stickers, photos without captions, etc.)
                            newest_seen = max(newest_seen, msg.id)
                            continue

                        if self.repo.raw_message_exists(int(channel.id), msg.id):
                            newest_seen = max(newest_seen, msg.id)
                            continue

                        message_date = msg.date or collected_at
                        post_link = _build_post_link(channel_username, msg.id)

                        self.repo.insert_raw_message(
                            channel_id=int(channel.id),
                            telegram_message_id=int(msg.id),
                            message_date=message_date,
                            message_text=text,
                            post_link=post_link,
                            collected_at=collected_at,
                        )
                        inserted += 1
                        newest_seen = max(newest_seen, msg.id)

                    if newest_seen > last_message_id and channel.id is not None:
                        self.repo.update_channel_last_message_id(int(channel.id), int(newest_seen))

                    per_channel_counts.append((f"@{channel_username}", inserted))
                    total_new += inserted

                    logger.info("Channel @%s: inserted %d new messages.", channel_username, inserted)
                except RPCError as e:
                    logger.exception("Telegram API error for channel '%s': %s", channel_username, e)
                    per_channel_counts.append((f"@{channel_username}", 0))
                    continue
                except Exception as e:
                    logger.exception("Failed collecting from channel '%s': %s", channel_username, e)
                    per_channel_counts.append((f"@{channel_username}", 0))
                    continue

        return CollectionResult(total_new_messages=total_new, per_channel_counts=per_channel_counts)

