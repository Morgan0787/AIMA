from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

from app.opportunity.hunter import OpportunityHunter
from app.core.utils import truncate_at_word


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


class OpportunityHunterCtaAndTruncateTests(unittest.TestCase):
    def _make_hunter(self) -> OpportunityHunter:
        config = SimpleNamespace(
            enabled=True,
            report_top_n=10,
            max_age_days=30,
            min_score=1,
            min_confidence=0.60,
            backfill_batch_size=100,
        )
        with patch("app.opportunity.hunter.get_config", return_value=SimpleNamespace(opportunity=config)):
            hunter = OpportunityHunter()
        hunter.repo = FakeRepo([])
        return hunter

    def test_past_event_with_only_hackathon_word_is_excluded(self) -> None:
        hunter = self._make_hunter()
        text = "Umummilliy AI Hackathon завершился, победители объявлены."
        # The word "хакатон" alone must NOT count as a call to action.
        self.assertFalse(hunter._has_meaningful_cta(text))
        result = hunter._assess_opportunity({}, text, None)
        self.assertFalse(result["is_opportunity"])

    def test_past_event_with_real_cta_still_has_cta(self) -> None:
        hunter = self._make_hunter()
        text = "Хакатон завершился, но подать заявку на следующий этап ещё можно."
        self.assertTrue(hunter._has_meaningful_cta(text))


class TruncateAtWordTests(unittest.TestCase):
    def test_no_truncation_when_short(self) -> None:
        self.assertEqual(truncate_at_word("короткий текст", 100), "короткий текст")

    def test_truncates_at_word_boundary(self) -> None:
        text = "Это длинное предложение с несколькими словами для обрезки"
        result = truncate_at_word(text, 20)
        self.assertNotIn("…", text)
        self.assertTrue(result.endswith("…"))
        self.assertLessEqual(len(result), 21)
        # No word should be cut in half: the result (minus the ellipsis) must
        # end on a complete word and be a prefix of the original.
        self.assertTrue(text.startswith(result[:-1]))

    def test_does_not_cut_mid_word(self) -> None:
        text = "однооченьдлинноесловобезпробелов"
        result = truncate_at_word(text, 10)
        # No space available, so it must cut at max_len and append ellipsis.
        self.assertTrue(result.endswith("…"))
        self.assertEqual(len(result), 11)

    def test_empty_and_none(self) -> None:
        self.assertEqual(truncate_at_word("", 10), "")
        self.assertEqual(truncate_at_word(None, 10), "")


if __name__ == "__main__":
    unittest.main()
