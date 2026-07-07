from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

from app.opportunity.hunter import OpportunityHunter


class FakeRepo:
    def __init__(self, rows):
        self.rows = rows

    def get_active_opportunities(self, **_: object):
        return list(self.rows)

    def decay_stale_active_opportunities(self, **_: object):
        return 0


class OpportunityHunterTests(unittest.TestCase):
    def test_build_report_deduplicates_similar_opportunity_rows(self) -> None:
        rows = [
            {
                "id": 1,
                "summary": "TechStars accelerator opens new cohort for climate startups. Apply by 12/10.",
                "channel_username": "news1",
                "post_link": "https://t.me/news1/1",
                "score": 9.5,
                "confidence_score": 0.92,
                "deadline_text": "",
                "opportunity_type": "accelerator",
                "metadata_json": json.dumps(
                    {
                        "summary": "TechStars accelerator opens new cohort for climate startups. Apply by 12/10.",
                        "confidence_score": 0.92,
                        "deadline_text": "",
                        "action_hint": "Подать заявку",
                    },
                    ensure_ascii=False,
                ),
            },
            {
                "id": 2,
                "summary": "Акселератор TechStars открывает новый cohort для climate startups. Заявки до 12/10.",
                "channel_username": "news2",
                "post_link": "https://t.me/news2/2",
                "score": 9.0,
                "confidence_score": 0.91,
                "deadline_text": "",
                "opportunity_type": "accelerator",
                "metadata_json": json.dumps(
                    {
                        "summary": "Акселератор TechStars открывает новый cohort для climate startups. Заявки до 12/10.",
                        "confidence_score": 0.91,
                        "deadline_text": "",
                        "action_hint": "Подать заявку",
                    },
                    ensure_ascii=False,
                ),
            },
        ]

        config = SimpleNamespace(
            enabled=True,
            report_top_n=10,
            max_age_days=30,
            min_score=1,
        )

        with patch("app.opportunity.hunter.get_config", return_value=SimpleNamespace(opportunity=config)):
            hunter = OpportunityHunter()
            hunter.repo = FakeRepo(rows)
            result = hunter.build_report()

        self.assertEqual(result.items_count, 1)
        self.assertEqual(result.new_items_count, 1)
        self.assertIn("TechStars", result.report_text)
        self.assertNotIn("https://t.me/news2/2", result.report_text)


if __name__ == "__main__":
    unittest.main()
