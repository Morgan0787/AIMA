import unittest
from unittest.mock import patch

from app.bot import telegram_bot
from app.search.search_engine import SearchResult


class TelegramBotResponseTests(unittest.TestCase):
    def _make_result(self, summary: str) -> SearchResult:
        return SearchResult(
            summary=summary,
            channel_username="@channel",
            post_link="https://example.com",
            message_date="2026-01-01",
            category="grant",
            score=1.0,
        )

    @patch.object(telegram_bot, "result_nav_keyboard", return_value=None)
    @patch.object(telegram_bot, "_format_results_block", side_effect=lambda title, results, include_deadline=True: title + "|" + "|".join(item.summary for item in results))
    @patch.object(telegram_bot.OPPORTUNITY_SERVICE, "get_top", return_value=[SearchResult(summary="top-result", channel_username="@channel", post_link="https://example.com", message_date="2026-01-01", category="grant", score=1.0)])
    @patch.object(telegram_bot.MEMORY, "get_interests", return_value=["hackathon"])
    def test_top_response_ignores_last_query(self, *_mocks):
        text, _ = telegram_bot._build_top_response(42)
        self.assertIn("top-result", text)

    @patch.object(telegram_bot, "result_nav_keyboard", return_value=None)
    @patch.object(telegram_bot, "_format_results_block", side_effect=lambda title, results, include_deadline=True: title + "|" + "|".join(item.summary for item in results))
    @patch.object(telegram_bot.OPPORTUNITY_SERVICE, "get_urgent", return_value=[SearchResult(summary="urgent-result", channel_username="@channel", post_link="https://example.com", message_date="2026-01-01", category="grant", score=1.0)])
    @patch.object(telegram_bot.MEMORY, "get_interests", return_value=["grant"])
    def test_urgent_response_ignores_last_query(self, *_mocks):
        text, _ = telegram_bot._build_urgent_response(42)
        self.assertIn("urgent-result", text)

    @patch.object(telegram_bot, "result_nav_keyboard", return_value=None)
    @patch.object(telegram_bot, "_format_results_block", side_effect=lambda title, results, include_deadline=True: title + "|" + "|".join(item.summary for item in results))
    @patch.object(telegram_bot.OPPORTUNITY_SERVICE, "get_deadlines", return_value=[SearchResult(summary="deadline-result", channel_username="@channel", post_link="https://example.com", message_date="2026-01-01", category="grant", score=1.0)])
    @patch.object(telegram_bot.MEMORY, "get_interests", return_value=["accelerator"])
    def test_deadline_response_ignores_last_query(self, *_mocks):
        text, _ = telegram_bot._build_deadline_response(42, 7)
        self.assertIn("deadline-result", text)


if __name__ == "__main__":
    unittest.main()
