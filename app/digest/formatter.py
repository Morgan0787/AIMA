"""
Digest formatting helpers for Jarvis v2 Core.

This module will format the digest text into a human-friendly structure
for display or export.
"""

from __future__ import annotations


def format_digest(raw_digest: str) -> str:
    """
    Apply any final formatting to the digest text.

    Right now this is a simple pass-through that strips leading and
    trailing whitespace.
    """
    # TODO: Add markdown/HTML formatting if needed.
    return raw_digest.strip()

