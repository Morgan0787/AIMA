"""
Simple data models for Jarvis v2 Core.

These use Python's built-in `dataclass` for clarity and type hints.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Channel:
    """Represents a Telegram channel being monitored."""

    id: Optional[int]
    telegram_id: Optional[int]
    last_message_id: Optional[int]
    username: Optional[str]
    title: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime


@dataclass
class RawMessage:
    """Represents a raw message collected from Telegram."""

    id: Optional[int]
    channel_id: int
    telegram_message_id: int
    post_link: Optional[str]
    message_text: str
    message_date: datetime
    collected_at: datetime
    content_hash: str
    is_processed: bool


@dataclass
class ProcessedMessage:
    """Represents a message after processing and analysis."""

    id: Optional[int]
    raw_message_id: int
    cleaned_text: str
    short_text: str
    is_duplicate: bool
    duplicate_of_raw_message_id: Optional[int]
    created_at: datetime
    classification: Optional[str]
    importance_score: Optional[float]
    metadata_json: Optional[str]
    processed_at: datetime
    included_in_digest: bool


@dataclass
class Digest:
    """Represents a generated daily digest."""

    id: Optional[int]
    digest_date: datetime
    title: Optional[str]
    content: str
    created_at: datetime
    published_to: Optional[str]
    metadata_json: Optional[str]



@dataclass
class Opportunity:
    """Represents an extracted opportunity from a Telegram message."""

    id: Optional[int]
    processed_message_id: int
    raw_message_id: int
    opportunity_type: str
    title: str
    summary: str
    channel_username: Optional[str]
    post_link: Optional[str]
    message_date: Optional[datetime]
    deadline_text: Optional[str]
    status: str
    score: float
    confidence_score: float
    source_category: Optional[str]
    created_at: datetime
    updated_at: datetime
    metadata_json: Optional[str]
