"""
Message cleaning utilities for Jarvis v2 Core.

Goal:
- Make Telegram messages easier to read and process
- Keep all important information (links, dates, numbers, names, etc.)
- Remove only obvious noise (extra spaces, repeated symbols)

We keep the logic simple and safe on purpose.
"""

from __future__ import annotations

import re


def _normalize_newlines(text: str) -> str:
    """Normalize different newline styles to simple '\\n'."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _normalize_whitespace(text: str) -> str:
    """
    Normalize spaces and empty lines while keeping structure.

    - Collapse multiple spaces/tabs inside a line into a single space
    - Remove leading/trailing spaces on each line
    - Reduce many empty lines to at most one empty line
    """
    text = _normalize_newlines(text)
    lines = text.split("\n")

    cleaned_lines = []
    empty_streak = 0

    for line in lines:
        # Collapse internal spaces and tabs, but keep line breaks.
        line = re.sub(r"[ \t]+", " ", line).strip()

        if line == "":
            empty_streak += 1
            # Allow at most one empty line in a row.
            if empty_streak > 1:
                continue
            cleaned_lines.append("")
        else:
            empty_streak = 0
            cleaned_lines.append(line)

    # Remove leading/trailing empty lines.
    while cleaned_lines and cleaned_lines[0] == "":
        cleaned_lines.pop(0)
    while cleaned_lines and cleaned_lines[-1] == "":
        cleaned_lines.pop()

    return "\n".join(cleaned_lines)


def _reduce_symbol_spam(text: str) -> str:
    """
    Reduce excessive symbol / emoji spam, conservatively.

    We only collapse runs of the same NON-alphanumeric symbol, and we
    keep up to 3 in a row (e.g. "!!!!!!" -> "!!!").

    This keeps normal text, numbers, and URLs intact.
    """

    def _replacer(match: re.Match[str]) -> str:
        char = match.group(1)
        return char * 3

    # [^\\w\\s] = "not a letter/number/underscore and not whitespace"
    return re.sub(r"([^\w\s])\1{3,}", _replacer, text)


def clean_text(text: str) -> str:
    """
    Clean a message string safely.

    Steps:
    - Normalize newlines
    - Normalize whitespace and empty lines
    - Reduce obvious symbol/emoji spam

    We do NOT:
    - Remove URLs
    - Remove numbers, dates, or amounts
    - Remove company or person names
    """
    if not text:
        return ""

    cleaned = _normalize_whitespace(text)
    cleaned = _reduce_symbol_spam(cleaned)

    return cleaned.strip()


def build_short_text(text: str, max_length: int = 800) -> str:
    """
    Build a shorter version of the text for future LLM use.

    Rules:
    - If the text is already short enough, return it as-is.
    - Otherwise, cut near `max_length`, but try to end at a
      natural boundary (paragraph, sentence, or newline).
    - Append "..." if we had to truncate.
    """
    if not text:
        return ""

    if len(text) <= max_length:
        return text

    cut = text[: max_length + 50]  # small buffer to find a nicer break

    # Try to end at a double newline (paragraph boundary).
    para_pos = cut.rfind("\n\n")
    if para_pos >= int(max_length * 0.6):
        cut = cut[:para_pos]
    else:
        # Try to end at a single newline.
        nl_pos = cut.rfind("\n")
        if nl_pos >= int(max_length * 0.6):
            cut = cut[:nl_pos]
        else:
            # Finally, try to end at a sentence boundary.
            dot_pos = cut.rfind(". ")
            if dot_pos >= int(max_length * 0.6):
                cut = cut[: dot_pos + 1]
            else:
                cut = cut[:max_length]

    return cut.rstrip() + "..."


