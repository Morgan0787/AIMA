"""
Ranking logic for Jarvis v2 Core.

This module will rank messages by importance or relevance for inclusion
in the daily digest.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class RankedMessage:
    """A message along with an importance score."""

    text: str
    score: float


def rank_messages(messages: List[str]) -> List[RankedMessage]:
    """
    Assign a simple ranking score to each message.

    For now, this is a placeholder that:
    - Assigns a fixed score (1.0) to each message
    - Keeps the original order
    """
    # TODO: Replace with a real ranking algorithm.
    return [RankedMessage(text=m, score=1.0) for m in messages]

