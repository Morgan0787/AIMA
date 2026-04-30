
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


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

SYNONYMS = {
    "hackathon": ["hackathon", "хакатон", "challenge", "contest", "competition", "startup competition", "ai contest"],
    "grant": ["grant", "грант", "funding", "финансирование", "subsidy", "субсидия", "scholarship", "fellowship"],
    "investor": ["investor", "investors", "vc", "venture", "fund", "фонды", "инвестор", "инвесторы"],
    "accelerator": ["accelerator", "акселератор", "incubator", "инкубатор", "batch"],
    "deadline": ["deadline", "дедлайн", "apply by", "registration closes"],
}

WEAK_TYPES = {"meetup", "expo", "exhibition", "retreat", "forum", "event", "tickets", "ticket_sales"}
STRONG_TYPES = {"grant", "hackathon", "competition", "accelerator", "fellowship", "program", "startup_program", "incubator", "scholarship"}

TYPE_WEIGHTS = {
    "grant": 4.0,
    "hackathon": 3.8,
    "competition": 3.5,
    "accelerator": 3.5,
    "incubator": 3.2,
    "startup_program": 3.2,
    "program": 2.6,
    "fellowship": 3.0,
    "scholarship": 3.0,
    "investor": 2.0,
    "event": -2.5,
    "meetup": -3.0,
    "expo": -3.0,
    "exhibition": -3.0,
    "retreat": -3.2,
    "forum": -2.8,
    "tickets": -4.0,
    "ticket_sales": -4.0,
}

QUERY_TYPE_ALIASES = {
    "hackathon": {"hackathon", "hackathons", "хакатон", "хакатоны"},
    "grant": {"grant", "grants", "грант", "гранты", "scholarship", "fellowship"},
    "accelerator": {"accelerator", "accelerators", "incubator", "incubators", "акселератор", "инкубатор"},
    "investor": {"investor", "investors", "vc", "venture", "fund", "funds", "инвестор", "инвесторы"},
}

WEAK_PHRASES = ("tickets", "билет", "retreat", "networking", "party", "форум", "meetup", "expo", "выставка", "митап", "investorlar kuni", "kuni", "global startup awards", "special session", "speaker", "повышение цен", "vc party", "venture forum")
STRONG_ACTION_WORDS = ("подать", "apply", "submit", "register", "зарегистр", "join", "участв", "принять участие", "подать заявку")
WEAK_EVENT_SIGNALS = ("tickets", "ticket", "билет", "retreat", "expo", "выставка", "networking", "party", "форум", "meetup", "митап", "speaker", "special session", "vip retreat", "sales", "продажи")
INVESTOR_STRONG_SIGNALS = (
    "investment readiness",
    "fundraising",
    "raise",
    "raised",
    "seed round",
    "pre-seed",
    "demo day",
    "pitch day",
    "pitch",
    "investor day",
    "vc",
    "venture fund",
    "angel investor",
    "fund announced",
    "investment",
    "fund",
    "venture",
    "инвест",
    "венчур",
    "фонд",
)
INVESTOR_NOISE_SIGNALS = (
    "interview",
    "подкаст",
    "разговор",
    "awards",
    "award",
    "director",
    "директор",
    "назначен",
    "поздрав",
    "navruz",
    "session",
    "speaker",
)
INVESTOR_ACTIONABLE_SIGNALS = (
    "fundraising",
    "raise",
    "raised",
    "seed round",
    "pre-seed",
    "demo day",
    "pitch day",
    "pitch",
    "investment readiness",
    "angel investor",
    "fund announced",
    "venture fund",
    "accelerator",
    "акселератор",
    "питч",
)


@dataclass
class SearchResult:
    summary: str
    channel_username: str
    post_link: str
    message_date: str
    category: str
    score: float
    action_hint: str = ""
    deadline_text: str = ""
    deadline_iso: str = ""


class SearchEngine:
    def __init__(self, db_path: Path | str):
        self.db_path = str(db_path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _safe_json(self, raw: Optional[str]) -> Dict[str, Any]:
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _normalize_channel(self, username: Optional[str]) -> str:
        name = (username or "unknown").strip()
        if name and not name.startswith("@"):
            name = f"@{name}"
        return name or "@unknown"

    def _normalize_text(self, value: str | None) -> str:
        return " ".join((value or "").strip().split())

    def _query_terms(self, query: str) -> List[str]:
        q = self._normalize_text(query).lower()
        if not q:
            return []
        terms = {q}
        pieces = [p for p in q.replace("/", " ").replace(",", " ").split() if p]
        terms.update(pieces)
        for key, values in SYNONYMS.items():
            if q == key or key in q or any(v in q for v in values):
                terms.update(values)
                terms.add(key)
        return [t for t in terms if t]

    def _is_weak_type(self, value: str | None) -> bool:
        text = (value or "").strip().lower()
        return text in WEAK_TYPES

    def _is_strong_type(self, value: str | None) -> bool:
        text = (value or "").strip().lower()
        return text in STRONG_TYPES

    def _type_weight(self, value: str | None) -> float:
        return TYPE_WEIGHTS.get((value or "").strip().lower(), 0.0)

    def _coerce_deadline(self, metadata: Dict[str, Any], deadline_text: str) -> Optional[datetime]:
        deadline_iso = str(metadata.get("deadline_iso") or "").strip()
        if deadline_iso:
            try:
                dt = datetime.fromisoformat(deadline_iso.replace("Z", "+00:00"))
                return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
            except ValueError:
                pass

        text = (deadline_text or "").lower().strip()
        if not text:
            return None

        now = datetime.now(UTC)

        m = re.search(r"(\d{1,2})\s*[-\u2013\u2014]\s*(\d{1,2})\s+([\u0400-\u04FFA-Za-z]+)(?:\s+(\d{4}))?", text)
        if m:
            day = int(m.group(1))
            month_word = m.group(3).lower()
            year = int(m.group(4) or now.year)
            month = None
            for key, value in MONTHS.items():
                if month_word.startswith(key):
                    month = value
                    break
            if month is not None:
                try:
                    dt = datetime(year, month, day, tzinfo=UTC)
                    if not m.group(4) and dt < now.replace(hour=0, minute=0, second=0, microsecond=0):
                        dt = datetime(year + 1, month, day, tzinfo=UTC)
                    return dt
                except ValueError:
                    return None

        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%d.%m.%Y", "%d-%m-%Y", "%d/%m/%Y"):
            try:
                return datetime.strptime(text, fmt).replace(tzinfo=UTC)
            except ValueError:
                pass

        m = re.search(r"(\d{1,2})[./-](\d{1,2})(?:[./-](\d{2,4}))?", text)
        if m:
            day = int(m.group(1))
            month = int(m.group(2))
            year = int(m.group(3) or now.year)
            if year < 100:
                year += 2000
            try:
                return datetime(year, month, day, tzinfo=UTC)
            except ValueError:
                return None

        m = re.search(r"(\d{1,2})\s+([А-Яа-яA-Za-z]+)(?:\s+(\d{4}))?", text)
        if m:
            day = int(m.group(1))
            month_word = m.group(2).lower()
            year = int(m.group(3) or now.year)
            month = None
            for key, value in MONTHS.items():
                if month_word.startswith(key):
                    month = value
                    break
            if month is not None:
                try:
                    dt = datetime(year, month, day, tzinfo=UTC)
                    if not m.group(3) and dt < now.replace(hour=0, minute=0, second=0, microsecond=0):
                        dt = datetime(year + 1, month, day, tzinfo=UTC)
                    return dt
                except ValueError:
                    return None
        return None

    def _row_to_result(self, row: sqlite3.Row) -> SearchResult:
        metadata = self._safe_json(row["metadata_json"]) if "metadata_json" in row.keys() else {}
        return SearchResult(
            summary=self._normalize_text(str(row["summary"] or "")),
            channel_username=self._normalize_channel(row["channel_username"] if "channel_username" in row.keys() else None),
            post_link=str(row["post_link"] or "").strip() if "post_link" in row.keys() else "",
            message_date=str(row["message_date"] or "").strip() if "message_date" in row.keys() else "",
            category=str(row["opportunity_type"] or metadata.get("category") or "opportunity").strip() if "opportunity_type" in row.keys() else str(metadata.get("category") or "message").strip(),
            score=float(row["score"] or row["importance_score"] or 0.0) if ("score" in row.keys() or "importance_score" in row.keys()) else 0.0,
            action_hint=str(metadata.get("action_hint") or metadata.get("action") or "").strip(),
            deadline_text=str(row["deadline_text"] or metadata.get("deadline_text") or metadata.get("deadline") or "").strip() if ("deadline_text" in row.keys() or metadata) else "",
            deadline_iso=str(metadata.get("deadline_iso") or "").strip(),
        )

    def _matches_terms(self, haystacks: Sequence[str], terms: Sequence[str]) -> bool:
        text = " || ".join((h or "").lower() for h in haystacks)
        return any(term.lower() in text for term in terms)

    def _infer_query_type(self, query: str, terms: Sequence[str]) -> str | None:
        q = self._normalize_text(query).lower()
        token_set = {q, *[t.lower() for t in terms]}
        for key, aliases in QUERY_TYPE_ALIASES.items():
            if any(alias in token_set or alias in q for alias in aliases):
                return key
        return None

    def _text_match_score(self, haystacks: Sequence[str], terms: Sequence[str]) -> float:
        lowered = [(h or "").lower() for h in haystacks if h]
        if not lowered:
            return 0.0
        score = 0.0
        for term in terms:
            t = term.lower().strip()
            if not t:
                continue
            for text in lowered:
                if t == text:
                    score += 4.0
                elif f" {t} " in f" {text} ":
                    score += 2.5
                elif t in text:
                    score += 1.0
        return score

    def _action_quality(self, item: SearchResult) -> float:
        action = (item.action_hint or "").strip().lower()
        if not action:
            return -1.2
        score = 0.6
        if len(action) >= 8:
            score += 0.2
        if any(word in action for word in STRONG_ACTION_WORDS):
            score += 0.8
        return score

    def _looks_like_weak_event(self, item: SearchResult, metadata: Dict[str, Any]) -> bool:
        category = (item.category or "").strip().lower()
        blob = " ".join(
            [
                (item.summary or "").lower(),
                (item.action_hint or "").lower(),
                str(metadata).lower(),
                category,
            ]
        )
        if self._is_weak_type(category):
            return True
        if category == "event" and any(signal in blob for signal in WEAK_EVENT_SIGNALS):
            return True
        return False

    def _deadline_boost(self, deadline_dt: Optional[datetime], now: datetime, *, for_urgent: bool = False) -> float:
        if deadline_dt is None:
            return -0.4 if for_urgent else 0.0
        delta_days = (deadline_dt - now).total_seconds() / 86400
        if delta_days < 0:
            return -6.0
        if delta_days <= 3:
            return 3.2 if for_urgent else 2.8
        if delta_days <= 7:
            return 2.2 if for_urgent else 1.6
        if delta_days <= 14:
            return 1.0
        return 0.2

    def _opportunity_rank(
        self,
        item: SearchResult,
        metadata: Dict[str, Any],
        now: Optional[datetime] = None,
        query_terms: Optional[Sequence[str]] = None,
        query_type: Optional[str] = None,
        for_urgent: bool = False,
    ) -> float:
        now = now or datetime.now(UTC)
        category = (item.category or "").strip().lower()
        summary = (item.summary or "").lower()
        deadline_dt = self._coerce_deadline(metadata, item.deadline_text)

        rank = float(item.score or 0.0)
        rank += self._type_weight(category)
        rank += self._action_quality(item)
        rank += self._deadline_boost(deadline_dt, now, for_urgent=for_urgent)

        if self._is_strong_type(category):
            rank += 1.2
        if self._looks_like_weak_event(item, metadata):
            rank -= 4.0
        if any(p in summary for p in WEAK_PHRASES):
            rank -= 2.5

        if query_terms:
            rank += self._text_match_score(
                [item.summary, item.category, item.action_hint, str(metadata)],
                query_terms,
            )

        if query_type == "hackathon" and category == "hackathon":
            rank += 8.0
        elif query_type == "grant" and category in {"grant", "scholarship", "fellowship"}:
            rank += 8.0
        elif query_type == "accelerator" and category in {"accelerator", "incubator", "program", "startup_program"}:
            rank += 8.0
        elif query_type == "investor":
            investor_signal = self._matches_terms([summary, item.action_hint, str(metadata)], SYNONYMS["investor"])
            if investor_signal and not self._is_weak_type(category):
                rank += 2.0
            else:
                rank -= 3.0

        return rank

    def _should_skip_for_query(self, item: SearchResult, metadata: Dict[str, Any], query_type: str | None) -> bool:
        category = (item.category or "").strip().lower()
        summary = (item.summary or "").lower()
        action = (item.action_hint or "").lower()

        if query_type == "hackathon" and category != "hackathon":
            return True
        if query_type == "grant" and category not in {"grant", "scholarship", "fellowship", "open_call"}:
            return True
        if query_type == "accelerator" and category not in {"accelerator", "incubator", "program", "startup_program"}:
            return True
        if query_type == "investor":
            investor_signal = self._matches_terms([summary, action, str(metadata)], SYNONYMS["investor"])
            if not investor_signal:
                return True
            if self._looks_like_weak_event(item, metadata):
                return True
            if any(p in summary for p in WEAK_PHRASES):
                return True
            blob = " ".join([summary, action, str(metadata).lower(), category])
            if any(noise in blob for noise in INVESTOR_NOISE_SIGNALS) and not any(signal in blob for signal in INVESTOR_STRONG_SIGNALS):
                return True
        return False

    def search_opportunities(self, query: str, limit: int = 5) -> List[SearchResult]:
        terms = self._query_terms(query)
        if not terms:
            return []

        query_type = self._infer_query_type(query, terms)

        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                    summary,
                    title,
                    channel_username,
                    post_link,
                    message_date,
                    opportunity_type,
                    score,
                    deadline_text,
                    metadata_json
                FROM opportunities
                WHERE status = 'active'
                ORDER BY score DESC, datetime(message_date) DESC, id DESC
                LIMIT 250;
                """
            )
            rows = cur.fetchall()
        finally:
            conn.close()

        now = datetime.now(UTC)
        ranked: List[tuple[float, SearchResult]] = []
        for row in rows:
            metadata = self._safe_json(row["metadata_json"])
            item = self._row_to_result(row)
            haystacks = [
                str(row["summary"] or ""),
                str(row["title"] or ""),
                str(row["opportunity_type"] or ""),
                str(metadata.get("action_hint") or metadata.get("action") or ""),
                str(metadata),
            ]
            match_score = self._text_match_score(haystacks, terms)
            if match_score <= 0:
                continue
            if self._should_skip_for_query(item, metadata, query_type):
                continue
            rank = self._opportunity_rank(item, metadata, now=now, query_terms=terms, query_type=query_type)
            if rank < 1.5:
                continue
            ranked.append((rank, item))

        ranked.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in ranked[: max(1, limit)]]


    def _content_match_allowed(
        self,
        item: SearchResult,
        metadata: Dict[str, Any],
        query_type: str | None,
        match_score: float,
    ) -> bool:
        category = (item.category or "").strip().lower()
        summary = (item.summary or "").lower()
        action = (item.action_hint or "").lower()
        blob = " ".join([summary, action, str(metadata).lower(), category])

        if match_score < 1.5:
            return False

        if query_type == "hackathon":
            return "hackathon" in blob or "хакатон" in blob

        if query_type == "grant":
            if self._looks_like_weak_event(item, metadata) or any(p in summary for p in WEAK_PHRASES):
                return False
            if any(term in summary for term in ["форум", "forum", "speaker", "special session", "venture market"]):
                return False
            if any(term in blob for term in ["grant", "грант", "scholarship", "fellowship", "subsidy", "субсидия"]):
                return True
            return (
                any(term in blob for term in ["open call", "набор", "прием заяв", "apply", "submit"])
                and ("program" in blob or "competition" in blob or "accelerator" in blob)
            )

        if query_type == "investor":
            if self._looks_like_weak_event(item, metadata) or any(p in summary for p in WEAK_PHRASES):
                return False
            if any(term in summary for term in ["global startup awards", "vc party", "venture forum", "special session", "speaker", "повышение цен"]):
                return False
            if any(term in blob for term in INVESTOR_NOISE_SIGNALS) and not any(term in blob for term in INVESTOR_STRONG_SIGNALS):
                return False
            return any(term in blob for term in INVESTOR_ACTIONABLE_SIGNALS)

        if query_type == "accelerator":
            if self._is_weak_type(category):
                return False
            return any(term in blob for term in ["accelerator", "акселератор", "incubator", "инкубатор", "batch", "program"])

        return not (self._looks_like_weak_event(item, metadata) and match_score < 3.0)

    def search_content(self, query: str, limit: int = 5) -> List[SearchResult]:
        terms = self._query_terms(query)
        if not terms:
            return []

        query_type = self._infer_query_type(query, terms)

        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                    pm.metadata_json,
                    pm.cleaned_text,
                    pm.importance_score,
                    rm.post_link,
                    rm.message_date,
                    ch.username AS channel_username
                FROM processed_messages pm
                JOIN raw_messages rm ON rm.id = pm.raw_message_id
                LEFT JOIN channels ch ON ch.id = rm.channel_id
                WHERE pm.is_duplicate = 0
                ORDER BY pm.importance_score DESC, datetime(rm.message_date) DESC, pm.id DESC
                LIMIT 300;
                """
            )
            rows = cur.fetchall()
        finally:
            conn.close()

        results: List[tuple[float, SearchResult]] = []
        for row in rows:
            metadata = self._safe_json(row["metadata_json"])
            summary = self._normalize_text(str(metadata.get("summary") or row["cleaned_text"] or ""))
            if not summary:
                continue
            haystacks = [summary, str(metadata.get("action") or ""), str(metadata.get("category") or ""), str(metadata)]
            match_score = self._text_match_score(haystacks, terms)
            if match_score <= 0:
                continue
            item = SearchResult(
                summary=summary[:220],
                channel_username=self._normalize_channel(row["channel_username"]),
                post_link=str(row["post_link"] or "").strip(),
                message_date=str(row["message_date"] or "").strip(),
                category=str(metadata.get("category") or "message").strip(),
                score=float(row["importance_score"] or 0.0),
                action_hint=str(metadata.get("action") or metadata.get("action_hint") or "").strip(),
                deadline_text=str(metadata.get("deadline_text") or metadata.get("deadline") or "").strip(),
                deadline_iso=str(metadata.get("deadline_iso") or "").strip(),
            )
            if not self._content_match_allowed(item, metadata, query_type, match_score):
                continue
            if self._should_skip_for_query(item, metadata, query_type):
                continue
            rank = item.score + match_score
            blob = summary.lower() + " " + str(metadata).lower()
            if query_type == "grant" and any(term in blob for term in ["grant", "грант", "scholarship", "fellowship", "open call", "apply", "submit"]):
                rank += 3.5
            if query_type == "investor":
                if any(noise in blob for noise in INVESTOR_NOISE_SIGNALS) and not any(signal in blob for signal in INVESTOR_STRONG_SIGNALS):
                    rank -= 3.0
                if any(term in blob for term in INVESTOR_ACTIONABLE_SIGNALS):
                    rank += 2.0
            results.append((rank, item))
        results.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in results[: max(1, limit)]]

    def get_upcoming_deadlines(self, days_ahead: int = 7, limit: int = 5) -> List[SearchResult]:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                    summary,
                    channel_username,
                    post_link,
                    message_date,
                    opportunity_type,
                    score,
                    deadline_text,
                    metadata_json
                FROM opportunities
                WHERE status = 'active'
                  AND TRIM(COALESCE(deadline_text, '')) != ''
                ORDER BY score DESC, datetime(message_date) DESC, id DESC;
                """
            )
            rows = cur.fetchall()
        finally:
            conn.close()

        now = datetime.now(UTC)
        upper = now + timedelta(days=max(1, days_ahead))
        results: List[tuple[datetime, float, SearchResult]] = []
        for row in rows:
            metadata = self._safe_json(row["metadata_json"])
            item = self._row_to_result(row)
            category = (item.category or "").strip().lower()
            if self._looks_like_weak_event(item, metadata) or category == "event":
                continue
            deadline_dt = self._coerce_deadline(metadata, item.deadline_text)
            if deadline_dt is None:
                continue
            if not (now <= deadline_dt <= upper):
                continue
            rank = self._opportunity_rank(item, metadata, now=now)
            if rank < 2.0:
                continue
            results.append((deadline_dt, -rank, item))

        results.sort(key=lambda x: (x[0], x[1]))
        return [item for _, _, item in results[: max(1, limit)]]

    def get_urgent_opportunities(self, limit: int = 5) -> List[SearchResult]:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                    summary,
                    channel_username,
                    post_link,
                    message_date,
                    opportunity_type,
                    score,
                    deadline_text,
                    metadata_json
                FROM opportunities
                WHERE status = 'active'
                ORDER BY score DESC, datetime(message_date) DESC, id DESC;
                """
            )
            rows = cur.fetchall()
        finally:
            conn.close()

        now = datetime.now(UTC)

        def collect(window_days: int) -> List[tuple[float, SearchResult]]:
            upper = now + timedelta(days=window_days)
            found: List[tuple[float, SearchResult]] = []
            for row in rows:
                metadata = self._safe_json(row["metadata_json"])
                item = self._row_to_result(row)
                if self._looks_like_weak_event(item, metadata):
                    continue
                deadline_dt = self._coerce_deadline(metadata, item.deadline_text)
                if deadline_dt is None or not (now <= deadline_dt <= upper):
                    continue
                rank = self._opportunity_rank(item, metadata, now=now, for_urgent=True)
                if rank < 2.0:
                    continue
                found.append((rank, item))
            found.sort(key=lambda x: x[0], reverse=True)
            return found[: max(1, limit)]

        results = collect(3)
        if not results:
            results = collect(7)
        return [item for _, item in results[: max(1, limit)]]

    def get_top_opportunities(self, limit: int = 5) -> List[SearchResult]:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT summary, channel_username, post_link, message_date, opportunity_type, score, deadline_text, metadata_json
                FROM opportunities
                WHERE status = 'active'
                ORDER BY score DESC, datetime(message_date) DESC, id DESC
                LIMIT 200;
                """
            )
            rows = cur.fetchall()
        finally:
            conn.close()

        now = datetime.now(UTC)
        ranked: List[tuple[float, SearchResult]] = []
        for row in rows:
            metadata = self._safe_json(row["metadata_json"])
            item = self._row_to_result(row)
            category = (item.category or "").strip().lower()
            if self._looks_like_weak_event(item, metadata) or category == "event":
                continue
            rank = self._opportunity_rank(item, metadata, now=now)
            if rank < 3.2:
                continue
            ranked.append((rank, item))

        ranked.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in ranked[: max(1, limit)]]
