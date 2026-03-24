"""
Message classification for Jarvis v2 Core.

This module will assign simple categories to messages, such as:
    - funding
    - events
    - jobs
    - news
    - other

Eventually, this will likely use the local LLM (Ollama).
For now, it contains a tiny placeholder.
"""

from __future__ import annotations

from typing import Optional


def classify_message(text: str) -> Optional[str]:
    """
    Classify a message into a rough category.

    For now, this is just a stub that always returns None.
    """
    # TODO: Implement proper classification logic (possibly using Ollama).
    return None

