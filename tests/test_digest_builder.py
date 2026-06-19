from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from app.digest.digest_builder import DigestBuilder


def _config(*, reuse_analyzed_messages: bool = False, digest_max_age_days: int = 3):
    return SimpleNamespace(
        digest_max_age_days=digest_max_age_days,
        debug=SimpleNamespace(reuse_analyzed_messages=reuse_analyzed_messages),
        opportunity=SimpleNamespace(max_age_days=14, min_score=4),
    )


def _candidate_row(
    processed_message_id: int,
    *,
    category: str,
    summary: str,
    importance_score: float = 0.9,
    priority_score: int = 8,
    channel_username: str = "startuphub",
    days_ago: int = 0,
) -> dict[str, object]:
    message_date = (datetime.now(UTC) - timedelta(days=days_ago)).replace(tzinfo=None)
    metadata = {
        "category": category,
        "summary": summary,
        "importance_score": importance_score,
        "priority_score": priority_score,
        "is_relevant": True,
    }
    return {
        "processed_message_id": processed_message_id,
        "channel_username": channel_username,
        "message_date": message_date,
        "post_link": f"https://t.me/{channel_username}/{processed_message_id}",
        "metadata_json": json.dumps(metadata, ensure_ascii=False),
    }


class FakeRepo:
    def __init__(
        self,
        *,
        candidate_rows_by_threshold: dict[float, list[dict[str, object]]] | None = None,
        recent_digests: list[dict[str, object]] | None = None,
        active_opportunities: list[dict[str, object]] | None = None,
    ) -> None:
        self.candidate_rows_by_threshold = candidate_rows_by_threshold or {}
        self.recent_digests = recent_digests or []
        self.active_opportunities = active_opportunities or []
        self.threshold_calls: list[float] = []

    def get_digest_candidates_with_threshold(self, *, min_importance: float, **_: object):
        self.threshold_calls.append(float(min_importance))
        for threshold in sorted(self.candidate_rows_by_threshold.keys(), reverse=True):
            if min_importance >= threshold:
                return list(self.candidate_rows_by_threshold[threshold])
        return []

    def get_recent_published_digests(self, **_: object):
        return list(self.recent_digests)

    def get_active_opportunities(self, **_: object):
        return list(self.active_opportunities)


class DigestBuilderTests(unittest.TestCase):
    def test_build_walks_normalized_importance_thresholds(self) -> None:
        strict_rows = [
            _candidate_row(1, category="grant", summary="Grant for climate startups", importance_score=0.7),
            _candidate_row(2, category="accelerator", summary="Accelerator cohort deadline", importance_score=0.72),
        ]
        relaxed_rows = strict_rows + [
            _candidate_row(3, category="hackathon", summary="Hackathon for founders", importance_score=0.5),
            _candidate_row(4, category="funding", summary="Funding round for AI startup", importance_score=0.48),
            _candidate_row(5, category="competition", summary="Competition for student teams", importance_score=0.46),
        ]
        fake_repo = FakeRepo(
            candidate_rows_by_threshold={
                0.6: strict_rows,
                0.45: relaxed_rows,
            }
        )

        with patch("app.digest.digest_builder.get_config", return_value=_config()):
            builder = DigestBuilder(max_items=10, candidate_limit=10)
            builder.repo = fake_repo
            result = builder.build()

        self.assertEqual(fake_repo.threshold_calls[:2], [0.6, 0.45])
        self.assertGreaterEqual(result.items_count, 2)
        self.assertTrue(result.digest_text)

    def test_build_keeps_fallback_opportunity_ids_publishable(self) -> None:
        fake_repo = FakeRepo(
            active_opportunities=[
                {
                    "processed_message_id": 42,
                    "summary": "Grant for climate founders",
                    "channel_username": "opportunities",
                    "deadline_text": "2026-07-01",
                    "post_link": "https://t.me/opportunities/42",
                }
            ]
        )

        with patch("app.digest.digest_builder.get_config", return_value=_config()):
            builder = DigestBuilder(max_items=10, candidate_limit=10)
            builder.repo = fake_repo
            result = builder.build()

        self.assertEqual(result.items_count, 1)
        self.assertEqual(result.included_processed_message_ids, [42])
        self.assertIn("Grant for climate founders", result.digest_text)

    def test_build_deduplicates_multilingual_duplicates(self) -> None:
        duplicate_rows = [
            _candidate_row(
                101,
                category="accelerator",
                summary="TechStars accelerator opens new cohort for climate startups. Apply by 12/10.",
                importance_score=0.92,
                priority_score=9,
                channel_username="news1",
            ),
            _candidate_row(
                102,
                category="accelerator",
                summary="Акселератор TechStars открывает новый cohort для climate startups. Заявки до 12/10.",
                importance_score=0.91,
                priority_score=9,
                channel_username="news2",
            ),
        ]
        anchor_row = _candidate_row(
            103,
            category="grant",
            summary="Grant for climate founders with deadline 12/10.",
            importance_score=0.75,
            priority_score=8,
            channel_username="news3",
        )
        fake_repo = FakeRepo(
            candidate_rows_by_threshold={
                0.6: duplicate_rows,
                0.45: duplicate_rows + [anchor_row],
            }
        )

        with patch("app.digest.digest_builder.get_config", return_value=_config()):
            builder = DigestBuilder(max_items=10, candidate_limit=10)
            builder.repo = fake_repo
            result = builder.build()

        self.assertEqual(result.items_count, 1)
        self.assertEqual(len(result.included_processed_message_ids), 1)
        self.assertIn("TechStars", result.digest_text)


if __name__ == "__main__":
    unittest.main()
