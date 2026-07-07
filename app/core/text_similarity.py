from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict

CYRILLIC_TRANSLITERATION = str.maketrans(
    {
        "а": "a",
        "б": "b",
        "в": "v",
        "г": "g",
        "д": "d",
        "е": "e",
        "ё": "e",
        "ж": "zh",
        "з": "z",
        "и": "i",
        "й": "y",
        "к": "k",
        "л": "l",
        "м": "m",
        "н": "n",
        "о": "o",
        "п": "p",
        "р": "r",
        "с": "s",
        "т": "t",
        "у": "u",
        "ф": "f",
        "х": "h",
        "ц": "ts",
        "ч": "ch",
        "ш": "sh",
        "щ": "shch",
        "ъ": "",
        "ы": "y",
        "ь": "",
        "э": "e",
        "ю": "yu",
        "я": "ya",
        "ў": "u",
        "қ": "k",
        "ғ": "g",
        "ҳ": "h",
        "і": "i",
    }
)


def normalize_summary(text: str) -> str:
    text = (text or "").lower()
    text = text.translate(CYRILLIC_TRANSLITERATION)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^\w\s]+", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tokenize(text: str) -> set[str]:
    return {token for token in text.split() if len(token) >= 3}


def character_ngrams(text: str, size: int = 3) -> set[str]:
    compact = re.sub(r"\s+", "", text)
    if not compact:
        return set()
    if len(compact) <= size:
        return {compact}
    return {compact[idx : idx + size] for idx in range(len(compact) - size + 1)}


def overlap_ratio(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / float(max(len(a), len(b)))


def build_signature(text: str) -> Dict[str, Any]:
    norm = normalize_summary(text)
    tokens = tokenize(norm)
    anchors = {token for token in tokens if len(token) >= 4 or any(ch.isdigit() for ch in token)}
    return {
        "norm": norm,
        "tokens": tokens,
        "anchors": anchors,
        "trigrams": character_ngrams(norm),
        "digits": set(re.findall(r"\d+", text or "")),
    }


def signature_similarity(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    if not a.get("norm") or not b.get("norm"):
        return 0.0
    if a["norm"] == b["norm"]:
        return 1.0
    return max(
        overlap_ratio(set(a.get("tokens", set())), set(b.get("tokens", set()))),
        overlap_ratio(set(a.get("anchors", set())), set(b.get("anchors", set()))),
        overlap_ratio(set(a.get("trigrams", set())), set(b.get("trigrams", set()))),
        overlap_ratio(set(a.get("digits", set())), set(b.get("digits", set()))),
    )
