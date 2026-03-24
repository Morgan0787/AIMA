"""
Deduplication helpers for Jarvis v2 Core.

This module will help identify and remove duplicate or near-duplicate
messages across channels and time.
"""

from __future__ import annotations

import hashlib
import difflib


def compute_content_hash(text: str) -> str:
    """
    Compute a stable content hash for a piece of text.

    We use SHA-256 over a normalized version of the text:
    - Strip leading/trailing whitespace
    - Convert to lowercase
    """
    normalized = (text or "").strip().lower().encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


def are_probable_duplicates(text_a: str, text_b: str) -> bool:
    """
    Decide if two cleaned texts are probably duplicates.

    Conservative rules:
    - If the normalized strings are exactly equal -> duplicate
    - Else, use difflib.SequenceMatcher to measure similarity:
      only treat as duplicate if similarity is very high (>= 0.98)

    This prefers missing some duplicates over accidentally merging
    two truly different messages.
    """
    a_norm = (text_a or "").strip()
    b_norm = (text_b or "").strip()

    if not a_norm or not b_norm:
        return False

    if a_norm == b_norm:
        return True

    # Very conservative fuzzy check.
    ratio = difflib.SequenceMatcher(None, a_norm, b_norm).ratio()
    return ratio >= 0.98


