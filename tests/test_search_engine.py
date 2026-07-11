from __future__ import annotations

import unittest
from datetime import UTC, datetime

from app.search.search_engine import SearchEngine, SearchResult


class SearchEngineCoerceDeadlineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = SearchEngine(":memory:")

    def test_247_style_returns_none(self) -> None:
        # "24/7" must be rejected as a non-deadline everywhere, including the
        # duplicate parser that used to live in _coerce_deadline.
        self.assertIsNone(self.engine._coerce_deadline({}, "24/7"))
        self.assertIsNone(self.engine._coerce_deadline({}, "Доступно 24/7"))
        self.assertIsNone(self.engine._coerce_deadline({}, "круглосуточно 24х7"))

    def test_deadline_iso_takes_precedence(self) -> None:
        iso = "2026-12-01T00:00:00"
        result = self.engine._coerce_deadline({"deadline_iso": iso}, "24/7")
        self.assertIsNotNone(result)
        self.assertEqual(result.year, 2026)
        self.assertEqual(result.month, 12)
        self.assertEqual(result.day, 1)

    def test_real_deadline_text_parsed(self) -> None:
        result = self.engine._coerce_deadline({}, "15 августа 2026")
        self.assertIsNotNone(result)
        self.assertEqual(result.year, 2026)
        self.assertEqual(result.month, 8)
        self.assertEqual(result.day, 15)

    def test_empty_returns_none(self) -> None:
        self.assertIsNone(self.engine._coerce_deadline({}, ""))
        self.assertIsNone(self.engine._coerce_deadline({}, None))


class BuildResultLineDeadlineTests(unittest.TestCase):
    def _make_item(self, deadline_text: str, deadline_iso: str = "") -> SearchResult:
        return SearchResult(
            summary="Test opportunity summary",
            channel_username="@channel",
            post_link="https://t.me/channel/1",
            message_date="2026-07-11",
            category="grant",
            score=9.0,
            action_hint="Подать заявку",
            deadline_text=deadline_text,
            deadline_iso=deadline_iso,
        )

    def test_247_not_shown_in_result_line(self) -> None:
        from app.bot.telegram_bot import _build_result_line

        item = self._make_item("24/7")
        line = _build_result_line(item, include_deadline=True)
        self.assertNotIn("Дедлайн", line)

    def test_valid_deadline_shown_in_result_line(self) -> None:
        from app.bot.telegram_bot import _build_result_line

        item = self._make_item("15 августа 2026")
        line = _build_result_line(item, include_deadline=True)
        self.assertIn("Дедлайн", line)

    def test_iso_only_deadline_shown(self) -> None:
        from app.bot.telegram_bot import _build_result_line

        item = self._make_item("15 августа 2026", deadline_iso="2026-08-15T00:00:00")
        line = _build_result_line(item, include_deadline=True)
        self.assertIn("Дедлайн", line)


if __name__ == "__main__":
    unittest.main()
