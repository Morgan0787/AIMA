from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.collector.telegram_collector import TelegramCollector


class FakeRepo:
    def get_all_channels(self):
        return []


class FakeClient:
    def __init__(self, *args, **kwargs) -> None:
        self.connected = False
        self.authorized = False

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    async def is_user_authorized(self) -> bool:
        return self.authorized

    async def start(self) -> bool:
        raise AssertionError("interactive login should not be used")


class TelegramCollectorTests(unittest.TestCase):
    def test_collect_returns_empty_result_when_not_authorized(self) -> None:
        collector = object.__new__(TelegramCollector)
        collector.config = SimpleNamespace(
            telegram=SimpleNamespace(api_id=1, api_hash="hash", channels=[], session_name="session")
        )
        collector.repo = FakeRepo()
        collector.channels = []
        collector.session_path = "session"

        fake_client = FakeClient()

        with patch("app.collector.telegram_collector.TelegramClient", return_value=fake_client):
            result = asyncio.run(collector._collect_async())

        self.assertEqual(result.total_new_messages, 0)
        self.assertEqual(result.per_channel_counts, [])
        self.assertFalse(fake_client.connected)


if __name__ == "__main__":
    unittest.main()
