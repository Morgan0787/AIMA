from __future__ import annotations

import unittest

from app.core.score_normalization import (
    HIGH_IMPORTANCE_THRESHOLD,
    importance_opportunity_contribution,
    normalize_importance_score,
)
from app.opportunity.hunter import OpportunityHunter
from app.opportunity.lifecycle import lifecycle_window_days


class ScoreNormalizationTests(unittest.TestCase):
    def test_normalize_importance_accepts_zero_to_one(self) -> None:
        self.assertEqual(normalize_importance_score(0.7), 0.7)
        self.assertEqual(normalize_importance_score(0.1), 0.1)

    def test_normalize_importance_maps_legacy_one_to_ten(self) -> None:
        self.assertEqual(normalize_importance_score(7), 0.7)
        self.assertEqual(normalize_importance_score(10), 1.0)

    def test_importance_opportunity_contribution_matches_legacy_weight(self) -> None:
        self.assertEqual(importance_opportunity_contribution(0.8), 4.0)
        self.assertEqual(importance_opportunity_contribution(8), 4.0)

    def test_high_importance_threshold_is_normalized(self) -> None:
        self.assertEqual(HIGH_IMPORTANCE_THRESHOLD, 0.7)


class OpportunityScoreTests(unittest.TestCase):
    def test_derive_score_uses_normalized_importance(self) -> None:
        hunter = OpportunityHunter()
        metadata = {
            "priority_score": 7,
            "importance_score": 0.8,
            "actionability_score": 6,
        }
        score = hunter._derive_score(metadata, "grant", None)
        # 7 + (0.8*5) + (6*0.5) + 1.0 boost = 15.0
        self.assertEqual(score, 15.0)

    def test_derive_score_supports_legacy_importance_values(self) -> None:
        hunter = OpportunityHunter()
        metadata = {
            "priority_score": 7,
            "importance_score": 8,
            "actionability_score": 6,
        }
        score = hunter._derive_score(metadata, "grant", None)
        self.assertEqual(score, 15.0)

    def test_assess_opportunity_boosts_confidence_for_high_importance(self) -> None:
        hunter = OpportunityHunter()
        base_metadata = {
            "category": "grant",
            "is_opportunity": True,
            "opportunity_type": "grant",
            "is_relevant": True,
            "priority_score": 4,
            "actionability_score": 4,
            "post_link": "https://t.me/test/1",
            "summary": "Подать заявку на грант",
        }
        low = hunter._assess_opportunity(
            {**base_metadata, "importance_score": 0.5},
            "Подать заявку на грант",
            "2026-06-01T00:00:00",
        )
        high = hunter._assess_opportunity(
            {**base_metadata, "importance_score": 0.75},
            "Подать заявку на грант",
            "2026-06-01T00:00:00",
        )
        self.assertGreater(high["confidence_score"], low["confidence_score"])


class DigestPriorityThresholdTests(unittest.TestCase):
    def test_priority_threshold_mapping(self) -> None:
        from app.digest.digest_builder import (
            FALLBACK_IMPORTANCE_THRESHOLD,
            RELAXED_IMPORTANCE_THRESHOLD,
            STRICT_IMPORTANCE_THRESHOLD,
            DigestBuilder,
        )

        builder = DigestBuilder()
        self.assertEqual(
            builder._priority_threshold_for_importance(STRICT_IMPORTANCE_THRESHOLD),
            6,
        )
        self.assertEqual(
            builder._priority_threshold_for_importance(RELAXED_IMPORTANCE_THRESHOLD),
            4,
        )
        self.assertEqual(
            builder._priority_threshold_for_importance(FALLBACK_IMPORTANCE_THRESHOLD),
            2,
        )


class LifecycleScoreThresholdTests(unittest.TestCase):
    def test_score_eight_still_unlocks_long_window_for_strong_opportunities(self) -> None:
        days = lifecycle_window_days(
            opportunity_type="grant",
            confidence_score=0.9,
            score=8.5,
            deadline_dt=None,
        )
        self.assertEqual(days, 60)

    def test_normalized_strong_opportunity_can_reach_score_eight(self) -> None:
        hunter = OpportunityHunter()
        metadata = {
            "priority_score": 6,
            "importance_score": 0.7,
            "actionability_score": 5,
        }
        score = hunter._derive_score(metadata, "grant", None)
        self.assertGreaterEqual(score, 8.0)


if __name__ == "__main__":
    unittest.main()
