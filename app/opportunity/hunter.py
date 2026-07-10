from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from ..core.config import get_config
from ..core.logger import get_logger
from ..core.score_normalization import (
    HIGH_IMPORTANCE_THRESHOLD,
    importance_opportunity_contribution,
    normalize_importance_score,
)
from ..core.text_similarity import (
    build_signature,
    signature_similarity,
)
from ..opportunity.lifecycle import assess_opportunity_lifecycle, parse_deadline_date
from ..storage.repository import Repository

logger = get_logger(__name__)

TYPE_LABELS = {
    "grant": "Гранты",
    "accelerator": "Акселераторы",
    "hackathon": "Хакатоны",
    "job": "Вакансии",
    "internship": "Стажировки",
    "event": "Практические события",
    "competition": "Конкурсы",
    "open_call": "Наборы и open call",
    "funding": "Инвестиции",
    "opportunity": "Возможности",
}

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

DEADLINE_CONTEXT_PATTERNS = [
    r"до\s+\d{1,2}\s+[А-Яа-яA-Za-z]+(?:\s+\d{4})?",
    r"дедлайн[:\s]+\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?",
    r"при[её]м\s+заяв[окки].{0,25}?\d{1,2}\s+[А-Яа-яA-Za-z]+(?:\s+\d{4})?",
    r"заявк[аи].{0,20}?до\s+\d{1,2}\s+[А-Яа-яA-Za-z]+(?:\s+\d{4})?",
    r"регистрац[ияи].{0,25}?\d{1,2}\s+[А-Яа-яA-Za-z]+(?:\s+\d{4})?",
    r"\b\d{1,2}\s+[А-Яа-яA-Za-z]+(?:\s+\d{4})?\b",
    r"\b\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?\b",
]

PAST_EVENT_MARKERS = [
    "прошел",
    "прошла",
    "прошли",
    "состоялся",
    "состоялась",
    "состоялись",
    "победители",
    "наградили",
    "представили",
    "завершился",
    "завершилась",
    "итоги",
]

CTA_KEYWORDS = [
    "подать заявку",
    "подача заявок",
    "заявки",
    "прием заявок",
    "зарегистрироваться",
    "регистрация",
    "register",
    "apply",
    "deadline",
    "дедлайн",
    "отправить резюме",
    "вакансия",
    "стажировка",
    "набор",
    "open call",
    "конкурс",
    "hackathon",
    "хакатон",
]

JOB_STRONG_KEYWORDS = [
    "ваканси",
    "hiring",
    "career",
    "отправить резюме",
    "ищем",
    "ищет",
    "we are hiring",
    "должность",
]

INTERNSHIP_KEYWORDS = ["стажиров", "internship", "trainee"]

OPEN_CALL_KEYWORDS = [
    "open call",
    "набор",
    "прием заяв",
    "заявки",
    "submit",
    "apply",
    "регистрац",
]

EVENT_KEYWORDS = [
    "вебинар",
    "сесси",
    "митап",
    "meetup",
    "forum",
    "expo",
    "мероприят",
    "встреч",
    "session",
    "demo day",
    "retreat",
    "workshop",
    "конференц",
]

FUTURE_EVENT_MARKERS = [
    "пройдет",
    "пройдёт",
    "состоится",
    "стартует",
    "откроется",
    "открыты продажи",
    "открыта регистрация",
    "регистрация открыта",
    "скоро пройдет",
    "скоро пройдёт",
    "будет",
    "invites",
]


@dataclass
class OpportunityBackfillStats:
    scanned_rows: int
    created_or_updated: int
    active_count: int


@dataclass
class OpportunityReportResult:
    report_text: str
    items_count: int
    new_items_count: int
    title: str


class OpportunityHunter:
    def __init__(self) -> None:
        self.repo = Repository()
        self.cfg = get_config().opportunity
        self.min_confidence = float(getattr(self.cfg, "min_confidence", 0.60) or 0.60)

    def _safe_metadata(self, raw: Optional[str]) -> Dict[str, Any]:
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _normalize_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", (text or "").strip())

    def _looks_like_past_event(self, text: str) -> bool:
        lower = self._normalize_text(text).lower()
        return any(marker in lower for marker in PAST_EVENT_MARKERS)


    def _looks_like_future_event(self, text: str) -> bool:
        lower = self._normalize_text(text).lower()
        return any(marker in lower for marker in FUTURE_EVENT_MARKERS)

    def _has_meaningful_cta(self, text: str) -> bool:
        lower = self._normalize_text(text).lower()
        return any(k in lower for k in CTA_KEYWORDS)

    def _looks_like_sale_or_ticketed_event(self, text: str) -> bool:
        lower = self._normalize_text(text).lower()
        sale_markers = [
            "открыты продажи",
            "билеты",
            "tickets",
            "ticket",
            "vip retreat",
            "expo",
            "retreat",
            "forum",
            "митап",
            "meetup",
        ]
        return any(marker in lower for marker in sale_markers)

    def _extract_reliable_deadline_text(self, text: str) -> str:
        text = self._normalize_text(text)
        if not text:
            return ""

        for pat in DEADLINE_CONTEXT_PATTERNS:
            m = re.search(pat, text, flags=re.IGNORECASE)
            if not m:
                continue
            candidate = m.group(0).strip(" .,:;-")[:120]
            parsed = self._parse_deadline_date(candidate, None)
            if parsed is not None:
                return candidate
        return ""

    def _parse_deadline_date(
        self, deadline_text: str, reference_date: Optional[datetime]
    ) -> Optional[datetime]:
        return parse_deadline_date(deadline_text, reference_date=reference_date)

    def _infer_opportunity_type(self, metadata: Dict[str, Any], text: str) -> str:
        category = str(metadata.get("opportunity_type") or metadata.get("category") or "").strip().lower()
        if category in {"grant", "accelerator", "hackathon", "job", "internship", "funding", "competition", "open_call"}:
            return category
        if category == "event":
            return "event"

        lower = (text or "").lower()
        checks = [
            ("grant", ["грант", "grant", "subsid", "субсид", "финансирован"]),
            ("accelerator", ["акселератор", "accelerator", "инкубац", "incubator", "batch"]),
            ("hackathon", ["хакатон", "hackathon"]),
            ("internship", INTERNSHIP_KEYWORDS),
            ("job", JOB_STRONG_KEYWORDS),
            ("competition", ["конкурс", "competition", "pitch day", "pitch"]),
            ("open_call", OPEN_CALL_KEYWORDS),
            ("event", EVENT_KEYWORDS),
            ("funding", ["investment", "инвестиц", "funding", "seed round", "venture"]),
        ]
        for kind, needles in checks:
            if any(n in lower for n in needles):
                return kind
        return ""

    def _infer_action_hint(self, opp_type: str, text: str) -> str:
        lower = (text or "").lower()
        if opp_type in {"grant", "accelerator", "open_call", "competition", "hackathon", "internship"}:
            return "Подать заявку"
        if opp_type == "job":
            return "Отправить резюме"
        if opp_type == "event":
            if "открыты продажи" in lower or "билеты" in lower or "tickets" in lower:
                return "Купить билет"
            return "Зарегистрироваться"
        if "зарегистр" in lower or "registration" in lower:
            return "Зарегистрироваться"
        if "заяв" in lower or "apply" in lower or "submit" in lower:
            return "Подать заявку"
        if "резюме" in lower or "cv" in lower:
            return "Отправить резюме"
        return "Подробнее по ссылке"

    def _assess_opportunity(
        self, metadata: Dict[str, Any], source_text: str, message_date: Optional[str]
    ) -> Dict[str, Any]:
        text = self._normalize_text(source_text)
        lower = text.lower()
        opp_type = self._infer_opportunity_type(metadata, text)
        category = str(metadata.get("category") or "").strip().lower()

        explicit_flag = metadata.get("is_opportunity") is True
        has_cta = self._has_meaningful_cta(text)
        deadline_text = str(metadata.get("deadline_text") or "").strip() or self._extract_reliable_deadline_text(text)
        deadline_dt = self._parse_deadline_date(deadline_text, None) if deadline_text else None
        has_link = bool(metadata.get("post_link"))
        is_relevant = bool(metadata.get("is_relevant", False))
        past_event = self._looks_like_past_event(text)
        future_event = self._looks_like_future_event(text)
        sale_or_ticketed_event = self._looks_like_sale_or_ticketed_event(text)

        try:
            priority = int(metadata.get("priority_score", 1))
        except (TypeError, ValueError):
            priority = 1
        importance = normalize_importance_score(metadata.get("importance_score", 0.3))
        try:
            actionability = int(metadata.get("actionability_score", 1))
        except (TypeError, ValueError):
            actionability = 1

        confidence = 0.0
        reasons: List[str] = []

        if explicit_flag:
            confidence += 0.35
            reasons.append("explicit_flag")
        if opp_type:
            confidence += 0.25
            reasons.append(f"type:{opp_type}")
        if has_cta:
            confidence += 0.20
            reasons.append("cta")
        if deadline_dt is not None:
            confidence += 0.15
            reasons.append("deadline")
        if is_relevant:
            confidence += 0.05
            reasons.append("relevant")
        if priority >= 7:
            confidence += 0.05
        if importance >= HIGH_IMPORTANCE_THRESHOLD:
            confidence += 0.05
        if actionability >= 6:
            confidence += 0.05

        if opp_type == "job" and not any(k in lower for k in JOB_STRONG_KEYWORDS):
            confidence -= 0.45
            reasons.append("weak_job")
        if opp_type == "event":
            if past_event and not has_cta:
                confidence -= 0.60
                reasons.append("past_event")
            if not future_event and deadline_dt is None and not sale_or_ticketed_event:
                confidence -= 0.35
                reasons.append("weak_event_signal")
            if sale_or_ticketed_event:
                confidence -= 0.35
                reasons.append("ticketed_event")
        if category == "ecosystem_news" and not has_cta and deadline_dt is None:
            confidence -= 0.30
            reasons.append("generic_news")
        if not has_link:
            confidence -= 0.05

        confidence = max(0.0, min(1.0, confidence))
        is_opportunity = confidence >= self.min_confidence and bool(opp_type or explicit_flag)
        if past_event and opp_type in {"event", "competition", "hackathon"} and not has_cta:
            is_opportunity = False
        if opp_type == "event" and not (future_event or deadline_dt is not None or sale_or_ticketed_event):
            is_opportunity = False
        if opp_type == "event" and sale_or_ticketed_event:
            is_opportunity = False

        action_hint = self._infer_action_hint(opp_type, text) if is_opportunity else ""
        score = self._derive_score(metadata, opp_type or "opportunity", message_date)
        if confidence < 0.75:
            score -= 1.0
        lifecycle_probe = {
            "opportunity_type": opp_type or "opportunity",
            "source_category": category,
            "score": score,
            "confidence_score": confidence,
            "deadline_text": deadline_text,
            "message_date": message_date,
            "created_at": message_date,
            "updated_at": message_date,
        }
        lifecycle = assess_opportunity_lifecycle(lifecycle_probe)
        status = lifecycle.next_status if lifecycle.is_stale else "active"

        return {
            "is_opportunity": is_opportunity,
            "opportunity_type": opp_type or "opportunity",
            "deadline_text": deadline_text,
            "deadline_iso": deadline_dt.isoformat(timespec="seconds") if deadline_dt else "",
            "action_hint": action_hint,
            "confidence_score": round(confidence, 3),
            "score": score,
            "status": status,
            "reasons": reasons,
        }

    def _derive_score(self, metadata: Dict[str, Any], opp_type: str, message_date: Optional[str]) -> float:
        try:
            priority = int(metadata.get("priority_score", 1))
        except (TypeError, ValueError):
            priority = 1
        importance_contribution = importance_opportunity_contribution(
            metadata.get("importance_score", 0.3)
        )
        try:
            actionability = int(metadata.get("actionability_score", 1))
        except (TypeError, ValueError):
            actionability = 1
        boost = 0.0
        if opp_type in {"grant", "accelerator", "hackathon", "job", "internship", "open_call", "competition"}:
            boost += 1.0
        if message_date:
            try:
                dt = datetime.fromisoformat(message_date.replace("Z", "+00:00"))
                if dt.tzinfo is not None:
                    dt = dt.astimezone(UTC).replace(tzinfo=None)
                age_days = max(0.0, (datetime.now(UTC).replace(tzinfo=None) - dt).total_seconds() / 86400.0)
                if age_days <= 7:
                    boost += 1.0
                elif age_days <= 30:
                    boost += 0.5
            except ValueError:
                pass
        return float(priority + importance_contribution + actionability * 0.5 + boost)

    def _refresh_existing_statuses(self) -> None:
        """Expire active opportunities whose deadline has already passed."""
        expired = self.repo.decay_stale_active_opportunities(limit=500)
        if expired:
            logger.info("Opportunity hunter expired %d stale opportunities.", expired)
        return

    def backfill(self) -> OpportunityBackfillStats:
        if not self.cfg.enabled:
            logger.info("Opportunity hunter disabled in config.")
            return OpportunityBackfillStats(
                scanned_rows=0,
                created_or_updated=0,
                active_count=self.repo.count_opportunities(active_only=True),
            )

        self._refresh_existing_statuses()
        rows = self.repo.get_analyzed_rows_for_opportunity_backfill(
            limit=self.cfg.backfill_batch_size,
            max_age_days=self.cfg.max_age_days,
            include_existing=True,
        )
        created_or_updated = 0
        skipped_low_confidence = 0

        for row in rows:
            metadata = self._safe_metadata(row.get("metadata_json"))
            metadata["post_link"] = row.get("post_link")
            source_text = " ".join(
                [
                    str(row.get("short_text") or ""),
                    str(row.get("cleaned_text") or ""),
                    str(row.get("message_text") or ""),
                    str(metadata.get("summary") or ""),
                    str(metadata.get("action_hint") or ""),
                ]
            ).strip()
            summary = str(metadata.get("summary") or "").strip() or self._normalize_text(source_text)[:140]
            if not summary:
                continue

            assessed = self._assess_opportunity(metadata, source_text, row.get("message_date"))
            if not assessed["is_opportunity"]:
                existing_id = row.get("existing_opportunity_id")
                if existing_id:
                    existing_metadata = self._safe_metadata(row.get("existing_opportunity_metadata_json"))
                    candidate = {
                        "opportunity_type": str(
                            existing_metadata.get("opportunity_type")
                            or existing_metadata.get("category")
                            or row.get("classification")
                            or ""
                        ).strip(),
                        "source_category": str(existing_metadata.get("category") or row.get("classification") or "").strip(),
                        "score": float(existing_metadata.get("score") or 0.0),
                        "confidence_score": float(existing_metadata.get("confidence_score") or 0.0),
                        "deadline_text": str(
                            assessed.get("deadline_text")
                            or existing_metadata.get("deadline_text")
                            or existing_metadata.get("deadline")
                            or ""
                        ).strip(),
                        "message_date": row.get("message_date"),
                        "created_at": row.get("message_date"),
                        "updated_at": row.get("message_date"),
                    }
                    lifecycle = assess_opportunity_lifecycle(candidate)
                    next_status = lifecycle.next_status if lifecycle.is_stale else "inactive"
                    self.repo.update_opportunity_status(opportunity_id=int(existing_id), status=next_status)
                skipped_low_confidence += 1
                continue

            opportunity_type = assessed["opportunity_type"]
            deadline_text = assessed["deadline_text"]
            action_hint = assessed["action_hint"]
            score = float(assessed["score"])
            confidence_score = float(assessed["confidence_score"])
            status = str(assessed["status"])

            enriched = dict(metadata)
            enriched.update(assessed)

            self.repo.upsert_opportunity(
                processed_message_id=int(row["processed_message_id"]),
                raw_message_id=int(row["raw_message_id"]),
                opportunity_type=opportunity_type,
                title=summary[:180],
                summary=summary[:220],
                channel_username=row.get("channel_username"),
                post_link=row.get("post_link"),
                message_date=row.get("message_date"),
                deadline_text=deadline_text[:120],
                status=status,
                score=score,
                confidence_score=confidence_score,
                source_category=str(metadata.get("category") or row.get("classification") or ""),
                metadata_json=json.dumps(enriched, ensure_ascii=False),
            )
            created_or_updated += 1

        active_count = self.repo.count_opportunities(active_only=True)
        logger.info(
            "Opportunity hunter backfill complete: scanned=%d created_or_updated=%d skipped=%d active=%d",
            len(rows),
            created_or_updated,
            skipped_low_confidence,
            active_count,
        )
        return OpportunityBackfillStats(
            scanned_rows=len(rows),
            created_or_updated=created_or_updated,
            active_count=active_count,
        )

    def build_report(self) -> OpportunityReportResult:
        if not self.cfg.enabled:
            return OpportunityReportResult(report_text="", items_count=0, new_items_count=0, title="")

        self._refresh_existing_statuses()
        rows = self.repo.get_active_opportunities(
            limit=max(self.cfg.report_top_n * 3, self.cfg.report_top_n),
            max_age_days=self.cfg.max_age_days,
            min_score=self.cfg.min_score,
        )
        if not rows:
            logger.info("Opportunity hunter found no active opportunities for report.")
            return OpportunityReportResult(report_text="", items_count=0, new_items_count=0, title="")

        filtered_rows: List[Dict[str, Any]] = []
        for row in rows:
            metadata = self._safe_metadata(row.get("metadata_json"))
            confidence = float(metadata.get("confidence_score", row.get("confidence_score") or 0.0) or 0.0)
            if confidence < self.min_confidence:
                continue
            row = dict(row)
            row["_meta"] = metadata
            filtered_rows.append(row)

        if not filtered_rows:
            logger.info("Opportunity hunter report skipped: no high-confidence opportunities.")
            return OpportunityReportResult(report_text="", items_count=0, new_items_count=0, title="")

        title = f"Jarvis Opportunity Hunter — {datetime.now(UTC).date().isoformat()}"
        now_naive = datetime.now(UTC).replace(tzinfo=None)

        def _urgency_score(row: Dict[str, Any]) -> float:
            metadata = row.get("_meta") or {}
            deadline_text = str(metadata.get("deadline_text") or row.get("deadline_text") or "").strip()
            deadline_dt = self._parse_deadline_date(deadline_text, None) if deadline_text else None
            urgency = 0.0
            if deadline_dt is not None:
                deadline_naive = deadline_dt.replace(tzinfo=None)
                now_naive_clean = (
                    now_naive.replace(tzinfo=None) if hasattr(now_naive, "replace") else now_naive
                )
                days_left = (deadline_naive - now_naive_clean).total_seconds() / 86400.0
                if 0 <= days_left <= 3:
                    urgency += 3.0
                elif 0 <= days_left <= 7:
                    urgency += 2.0
                elif 0 <= days_left <= 14:
                    urgency += 1.0
            return float(row.get("score") or 0.0) + urgency

        filtered_rows.sort(key=_urgency_score, reverse=True)

        deduped_rows: List[Dict[str, Any]] = []
        kept_signatures: List[Dict[str, Any]] = []
        removed_duplicates = 0
        for row in filtered_rows:
            summary = str(row.get("summary") or "").strip()
            row_signature = build_signature(summary)
            is_duplicate = False
            for kept_row, kept_signature in zip(deduped_rows, kept_signatures):
                if signature_similarity(row_signature, kept_signature) >= 0.6:
                    is_duplicate = True
                    if (row.get("score") or 0.0) > (kept_row.get("score") or 0.0):
                        kept_idx = deduped_rows.index(kept_row)
                        deduped_rows[kept_idx] = row
                        kept_signatures[kept_idx] = row_signature
                    break
            if is_duplicate:
                removed_duplicates += 1
                continue
            deduped_rows.append(row)
            kept_signatures.append(row_signature)

        filtered_rows = deduped_rows
        logger.info("Opportunity hunter removed %d duplicate/similar opportunities.", removed_duplicates)

        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for row in filtered_rows:
            grouped.setdefault(row.get("opportunity_type") or "opportunity", []).append(row)

        lines: List[str] = [title, ""]
        idx = 1
        urgent_rows: List[Dict[str, Any]] = []
        for row in filtered_rows:
            metadata = row.get("_meta") or {}
            deadline_text = str(metadata.get("deadline_text") or row.get("deadline_text") or "").strip()
            deadline_dt = self._parse_deadline_date(deadline_text, None) if deadline_text else None
            if deadline_dt is None:
                continue
            deadline_naive_rep = deadline_dt.replace(tzinfo=None) if deadline_dt else None
            now_naive_rep = now_naive.replace(tzinfo=None) if hasattr(now_naive, "replace") else now_naive
            days_left = (
                (deadline_naive_rep - now_naive_rep).total_seconds() / 86400.0
                if (deadline_naive_rep and now_naive_rep)
                else 0.0
            )
            if 0 <= days_left <= 7:
                urgent_rows.append(row)

        if urgent_rows:
            lines.append("🔥 Срочно")
            lines.append("-------")
            for row in urgent_rows[: min(3, self.cfg.report_top_n)]:
                metadata = row.get("_meta") or {}
                lines.append(f"{idx}. {row.get('summary')}")
                channel = row.get("channel_username") or "@unknown"
                lines.append(f"   Источник: @{str(channel).lstrip('@')}")
                deadline_text = str(metadata.get("deadline_text") or row.get("deadline_text") or "").strip()
                if deadline_text and self._parse_deadline_date(deadline_text, None) is not None:
                    lines.append(f"   Дедлайн/дата: {deadline_text}")
                action_hint = str(metadata.get('action_hint') or '').strip() or "Подробнее по ссылке"
                lines.append(f"   Действие: {action_hint}")
                if row.get("post_link"):
                    lines.append(f"   Ссылка: {row.get('post_link')}")
                lines.append("")
                idx += 1

        order = [
            "grant",
            "accelerator",
            "hackathon",
            "internship",
            "job",
            "competition",
            "open_call",
            "event",
            "funding",
            "opportunity",
        ]
        seen = set()
        urgent_links = {row.get('post_link') for row in urgent_rows if row.get('post_link')}

        for key in order + [k for k in grouped.keys() if k not in order]:
            if key not in grouped or key in seen:
                continue
            seen.add(key)
            section_rows = grouped[key][: self.cfg.report_top_n]
            if not section_rows:
                continue
            label = TYPE_LABELS.get(key, key.upper())
            lines.append(label)
            lines.append("-" * len(label))
            for row in section_rows:
                if row.get('post_link') in urgent_links:
                    continue
                lines.append(f"{idx}. {row.get('summary')}")
                channel = row.get("channel_username") or "@unknown"
                lines.append(f"   Источник: @{str(channel).lstrip('@')}")
                metadata = row.get("_meta") or {}
                deadline_text = str(metadata.get("deadline_text") or row.get("deadline_text") or "").strip()
                if deadline_text and self._parse_deadline_date(deadline_text, None) is not None:
                    lines.append(f"   Дедлайн/дата: {deadline_text}")
                action_hint = str(metadata.get("action_hint") or "").strip() or "Подробнее по ссылке"
                lines.append(f"   Действие: {action_hint}")
                if row.get("post_link"):
                    lines.append(f"   Ссылка: {row.get('post_link')}")
                lines.append("")
                idx += 1

        report_text = "\n".join(lines).strip()
        return OpportunityReportResult(
            report_text=report_text,
            items_count=len(filtered_rows),
            new_items_count=len(filtered_rows),
            title=title,
        )
