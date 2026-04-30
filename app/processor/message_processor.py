"""
Message processing pipeline for Jarvis v2 Core (Step 3).

Flow:
- Load unprocessed records from `raw_messages`
- Clean text safely
- Build a shorter `short_text` variant
- Detect duplicates conservatively
- Store results into `processed_messages`

Important:
- We NEVER modify or delete rows from `raw_messages`.
- We only mark them as processed via `is_processed = 1`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Dict

from .cleaner import clean_text, build_short_text
from .deduplicator import compute_content_hash, are_probable_duplicates
from ..core.logger import get_logger
from ..storage.repository import Repository


logger = get_logger(__name__)

HEURISTIC_KEYWORDS = [
    "грант",
    "фонд",
    "вакансия",
    "работа",
    "хакатон",
    "конкурс",
    "apply",
    "deadline",
    "funding",
    "opportunity",
    "job",
    "invest",
    "startup",
]

EMOJI_AND_SYMBOLS_RE = re.compile(r"[^\w\s]+", flags=re.UNICODE)
MULTISPACE_RE = re.compile(r"\s+")


@dataclass
class ProcessingStats:
    """Summary of a processing run."""

    processed_count: int
    duplicate_count: int


class MessageProcessor:
    """
    MessageProcessor pulls new rows from `raw_messages` and writes
    cleaned results into `processed_messages`.
    """

    def __init__(self, batch_limit: int = 500) -> None:
        self.repo = Repository()
        self.batch_limit = batch_limit

    def _contains_heuristic_keyword(self, text: str) -> bool:
        lowered = (text or "").lower()
        return any(keyword in lowered for keyword in HEURISTIC_KEYWORDS)

    def _normalize_for_dedup(self, text: str) -> str:
        lowered = (text or "").lower()
        no_symbols = EMOJI_AND_SYMBOLS_RE.sub(" ", lowered)
        return MULTISPACE_RE.sub(" ", no_symbols).strip()

    def process(self) -> ProcessingStats:
        """
        Run one processing pass.

        Steps:
        - Fetch a batch of unprocessed raw messages.
        - For each message:
          - Clean text.
          - Build `short_text`.
          - Check if we already processed this raw_message_id.
          - Check for duplicates:
              * Exact match in `processed_messages` by cleaned_text.
              * Very similar text to something already in this batch.
          - Insert into `processed_messages`.
          - Mark the raw message as processed.
        """
        raw_messages = self.repo.get_unprocessed_raw_messages(limit=self.batch_limit)
        if not raw_messages:
            logger.info("No unprocessed raw messages found.")
            return ProcessingStats(processed_count=0, duplicate_count=0)

        logger.info("Processing %d raw messages...", len(raw_messages))

        processed_count = 0
        duplicate_count = 0

        # Track texts seen in this batch to improve duplicate detection
        # without scanning the whole database.
        batch_texts: Dict[str, int] = {}  # content_hash -> raw_message_id
        batch_cleaned_by_id: Dict[int, str] = {}

        for raw in raw_messages:
            try:
                if not raw.message_text or not raw.message_text.strip():
                    # Skip completely empty messages but mark them as processed
                    # so we don't keep hitting them on every run.
                    logger.info(
                        "Skipping empty raw message id=%s (channel_id=%s).",
                        raw.id,
                        raw.channel_id,
                    )
                    self.repo.mark_raw_message_processed(int(raw.id))
                    continue

                cleaned = clean_text(raw.message_text)
                if not cleaned:
                    logger.info(
                        "Skipping message id=%s after cleaning produced empty text.",
                        raw.id,
                    )
                    self.repo.mark_raw_message_processed(int(raw.id))
                    continue

                short = build_short_text(cleaned)
                normalized_cleaned = self._normalize_for_dedup(cleaned)

                # Safety: do not double-insert if we already processed this ID.
                if self.repo.processed_message_exists(int(raw.id)):
                    logger.info(
                        "Raw message id=%s is already in processed_messages, skipping.",
                        raw.id,
                    )
                    self.repo.mark_raw_message_processed(int(raw.id))
                    continue

                # Coarse heuristic filter: skip obvious noise quickly.
                # We still mark raw row as processed to avoid reprocessing it.
                if not self._contains_heuristic_keyword(cleaned):
                    logger.info(
                        "Heuristic filter skipped raw message id=%s (no target keywords).",
                        raw.id,
                    )
                    self.repo.mark_raw_message_processed(int(raw.id))
                    continue

                is_duplicate = False
                duplicate_of_raw_id = None

                # 1) Check for exact duplicate across all past messages.
                existing = self.repo.find_duplicate_processed_message(cleaned)
                if existing is None and normalized_cleaned and normalized_cleaned != cleaned:
                    existing = self.repo.find_duplicate_processed_message(normalized_cleaned)
                if existing is not None:
                    is_duplicate = True
                    duplicate_of_raw_id = existing.raw_message_id
                else:
                    # 2) Check inside this batch using hash + fuzzy comparison.
                    content_hash = compute_content_hash(normalized_cleaned or cleaned)
                    if content_hash in batch_texts:
                        other_raw_id = batch_texts[content_hash]
                        other_text = batch_cleaned_by_id.get(other_raw_id, "")
                        if are_probable_duplicates(normalized_cleaned or cleaned, other_text):
                            is_duplicate = True
                            duplicate_of_raw_id = other_raw_id

                if not is_duplicate:
                    db_candidate = self.repo.find_similar_processed_message(
                        normalized_cleaned or cleaned
                    )
                    if db_candidate is not None:
                        is_duplicate = True
                        duplicate_of_raw_id = db_candidate.raw_message_id

                processed_at = datetime.utcnow()
                self.repo.insert_processed_message(
                    raw_message_id=int(raw.id),
                    cleaned_text=cleaned,
                    short_text=short,
                    is_duplicate=is_duplicate,
                    duplicate_of_raw_message_id=duplicate_of_raw_id,
                    processed_at=processed_at,
                )

                # Mark as processed in the raw table.
                self.repo.mark_raw_message_processed(int(raw.id))

                processed_count += 1
                if is_duplicate:
                    duplicate_count += 1

                # Save in batch trackers for later comparisons in this run.
                content_hash = compute_content_hash(normalized_cleaned or cleaned)
                batch_texts.setdefault(content_hash, int(raw.id))
                batch_cleaned_by_id[int(raw.id)] = normalized_cleaned or cleaned

            except Exception as exc:  # noqa: BLE001
                # Never crash the whole run because of a single bad row.
                logger.exception(
                    "Failed to process raw message id=%s: %s",
                    getattr(raw, "id", None),
                    exc,
                )
                # We do NOT mark it as processed here so you can inspect it later.

        logger.info(
            "Processing finished. Total processed: %d, duplicates: %d",
            processed_count,
            duplicate_count,
        )
        return ProcessingStats(processed_count=processed_count, duplicate_count=duplicate_count)

