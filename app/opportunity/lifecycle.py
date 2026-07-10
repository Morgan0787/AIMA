from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Mapping


MONTHS = {
    "январ": 1,
    "феврал": 2,
    "март": 3,
    "апрел": 4,
    "мая": 5,
    "май": 5,
    "июн": 6,
    "июл": 7,
    "август": 8,
    "сентябр": 9,
    "октябр": 10,
    "ноябр": 11,
    "декабр": 12,
}

WEAK_OPPORTUNITY_TYPES = {
    "event",
    "meetup",
    "expo",
    "exhibition",
    "retreat",
    "forum",
    "tickets",
    "ticket_sales",
}

STRONG_OPPORTUNITY_TYPES = {
    "grant",
    "hackathon",
    "competition",
    "accelerator",
    "incubator",
    "startup_program",
    "program",
    "fellowship",
    "scholarship",
}


@dataclass(frozen=True)
class OpportunityLifecycleDecision:
    is_stale: bool
    next_status: str
    age_days: float | None
    deadline_dt: datetime | None


def parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        raw = str(value).strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def parse_deadline_date(deadline_text: str, reference_date: datetime | None = None) -> datetime | None:
    if not deadline_text:
        return None

    reference = reference_date or datetime.now(UTC)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=UTC)
    local_reference = reference.astimezone(UTC).replace(tzinfo=None)

    text = deadline_text.lower().strip()
    if not text:
        return None

    no_deadline_phrases = (
        "24/7",
        "24х7",
        "круглосуточно",
        "постоянно",
        "без дедлайна",
        "без ограничений",
        "бессрочно",
        "always",
        "ongoing",
        "rolling",
        "continuously",
        "открыто всегда",
        "open ended",
        "open-ended",
    )
    if any(phrase in text for phrase in no_deadline_phrases):
        return None

    import re

    match = re.search(r"(\d{1,2})\s*[-\u2013\u2014]\s*(\d{1,2})\s+([\u0400-\u04FFA-Za-z]+)(?:\s+(\d{4}))?", text)
    if match:
        day = int(match.group(1))
        month_word = match.group(3).lower()
        year = int(match.group(4) or local_reference.year)
        month = None
        for key, value in MONTHS.items():
            if month_word.startswith(key):
                month = value
                break
        if month is not None:
            try:
                parsed = datetime(year, month, day, tzinfo=UTC)
                if not match.group(4) and parsed.replace(tzinfo=None) < local_reference.replace(
                    hour=0, minute=0, second=0, microsecond=0
                ):
                    parsed = datetime(year + 1, month, day, tzinfo=UTC)
                return parsed
            except ValueError:
                return None

    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%d.%m.%Y", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=UTC)
        except ValueError:
            pass

    match = re.search(r"(\d{1,2})[./-](\d{1,2})(?:[./-](\d{2,4}))?", text)
    if match:
        day = int(match.group(1))
        month = int(match.group(2))
        year = int(match.group(3) or local_reference.year)
        if year < 100:
            year += 2000
        try:
            return datetime(year, month, day, tzinfo=UTC)
        except ValueError:
            return None

    match = re.search(r"(\d{1,2})\s+([\u0400-\u04FFA-Za-z]+)(?:\s+(\d{4}))?", text)
    if match:
        day = int(match.group(1))
        month_word = match.group(2).lower()
        year = int(match.group(3) or local_reference.year)
        month = None
        for key, value in MONTHS.items():
            if month_word.startswith(key):
                month = value
                break
        if month is not None:
            try:
                parsed = datetime(year, month, day, tzinfo=UTC)
                if not match.group(3) and parsed.replace(tzinfo=None) < local_reference.replace(
                    hour=0, minute=0, second=0, microsecond=0
                ):
                    parsed = datetime(year + 1, month, day, tzinfo=UTC)
                return parsed
            except ValueError:
                return None

    return None


def _first_datetime(*values: Any) -> datetime | None:
    for value in values:
        parsed = parse_datetime(value)
        if parsed is not None:
            return parsed
    return None


def _row_value(row: Mapping[str, Any], key: str) -> Any:
    if hasattr(row, "get"):
        return row.get(key)  # type: ignore[call-arg]
    try:
        return row[key]
    except Exception:
        return None


def _opportunity_category(row: Mapping[str, Any]) -> str:
    category = str(_row_value(row, "opportunity_type") or _row_value(row, "source_category") or "").strip().lower()
    return category


def lifecycle_window_days(
    *,
    opportunity_type: str,
    confidence_score: float,
    score: float,
    deadline_dt: datetime | None,
) -> int:
    if deadline_dt is not None:
        return 3650

    if opportunity_type in WEAK_OPPORTUNITY_TYPES:
        return 10
    if confidence_score >= 0.85 and score >= 8 and opportunity_type in STRONG_OPPORTUNITY_TYPES:
        return 60
    if confidence_score >= 0.75:
        return 30
    if confidence_score >= 0.6:
        return 21
    return 14


def assess_opportunity_lifecycle(
    row: Mapping[str, Any],
    *,
    now: datetime | None = None,
) -> OpportunityLifecycleDecision:
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    current = current.astimezone(UTC)

    metadata_deadline = ""
    metadata_raw = _row_value(row, "metadata_json")
    if metadata_raw:
        try:
            import json

            metadata = json.loads(str(metadata_raw))
        except (TypeError, ValueError, json.JSONDecodeError):
            metadata = {}
        if isinstance(metadata, dict):
            metadata_deadline = str(metadata.get("deadline_text") or metadata.get("deadline") or "").strip()
    else:
        metadata = {}

    deadline_text = str(_row_value(row, "deadline_text") or metadata_deadline or "").strip()
    deadline_dt = parse_deadline_date(deadline_text, reference_date=current) if deadline_text else None
    if deadline_dt is not None and deadline_dt < current:
        return OpportunityLifecycleDecision(
            is_stale=True,
            next_status="expired",
            age_days=None,
            deadline_dt=deadline_dt,
        )

    source_dt = _first_datetime(
        _row_value(row, "message_date"),
        _row_value(row, "created_at"),
        _row_value(row, "updated_at"),
    )
    if source_dt is None:
        return OpportunityLifecycleDecision(
            is_stale=False,
            next_status="active",
            age_days=None,
            deadline_dt=deadline_dt,
        )

    age_days = max(0.0, (current - source_dt).total_seconds() / 86400.0)
    confidence_score = 0.0
    score = 0.0
    try:
        confidence_score = float(_row_value(row, "confidence_score") or 0.0)
    except (TypeError, ValueError):
        confidence_score = 0.0
    try:
        score = float(_row_value(row, "score") or 0.0)
    except (TypeError, ValueError):
        score = 0.0

    opportunity_type = _opportunity_category(row)
    max_age_days = lifecycle_window_days(
        opportunity_type=opportunity_type,
        confidence_score=confidence_score,
        score=score,
        deadline_dt=deadline_dt,
    )

    if deadline_dt is None and age_days > float(max_age_days):
        next_status = "expired" if confidence_score >= 0.75 else "inactive"
        return OpportunityLifecycleDecision(
            is_stale=True,
            next_status=next_status,
            age_days=age_days,
            deadline_dt=None,
        )

    return OpportunityLifecycleDecision(
        is_stale=False,
        next_status="active",
        age_days=age_days,
        deadline_dt=deadline_dt,
    )
