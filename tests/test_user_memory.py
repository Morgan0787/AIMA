import asyncio
import unittest

from app.bot import telegram_bot


class UserMemoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.memory = telegram_bot.MEMORY
        self.user_id = 4242424242
        conn = self.memory._connect()
        conn.execute("DELETE FROM users WHERE user_id=?", (self.user_id,))
        conn.commit()
        conn.close()

    def test_register_user_and_digest_opt_in_flow(self) -> None:
        self.memory.register_user(self.user_id)
        conn = self.memory._connect()
        row = conn.execute("SELECT user_id FROM users WHERE user_id=?", (self.user_id,)).fetchone()
        conn.close()
        self.assertIsNotNone(row)

        self.memory.set_digest_opt_in(self.user_id, False)
        self.assertNotIn(self.user_id, self.memory.get_opted_in_users())

        self.memory.set_digest_opt_in(self.user_id, True)
        self.assertIn(self.user_id, self.memory.get_opted_in_users())


class TelegramBotCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_registers_user(self) -> None:
        user_id = 4242424243
        memory = telegram_bot.MEMORY
        conn = memory._connect()
        conn.execute("DELETE FROM users WHERE user_id=?", (user_id,))
        conn.commit()
        conn.close()

        class DummyMessage:
            def __init__(self) -> None:
                self.replies = []

            async def reply_text(self, text, reply_markup=None, disable_web_page_preview=True):
                self.replies.append((text, reply_markup, disable_web_page_preview))

        class DummyUser:
            def __init__(self, user_id: int) -> None:
                self.id = user_id

        class DummyUpdate:
            def __init__(self, user_id: int) -> None:
                self.effective_user = DummyUser(user_id)
                self.message = DummyMessage()

        update = DummyUpdate(user_id)
        await telegram_bot.start(update, None)

        conn = memory._connect()
        row = conn.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,)).fetchone()
        conn.close()
        self.assertIsNotNone(row)

    async def test_subscribe_and_unsubscribe_toggle_opt_in(self) -> None:
        user_id = 4242424244
        memory = telegram_bot.MEMORY
        conn = memory._connect()
        conn.execute("DELETE FROM users WHERE user_id=?", (user_id,))
        conn.commit()
        conn.close()

        class DummyMessage:
            def __init__(self) -> None:
                self.replies = []

            async def reply_text(self, text, reply_markup=None, disable_web_page_preview=True):
                self.replies.append((text, reply_markup, disable_web_page_preview))

        class DummyUser:
            def __init__(self, user_id: int) -> None:
                self.id = user_id

        class DummyUpdate:
            def __init__(self, user_id: int) -> None:
                self.effective_user = DummyUser(user_id)
                self.message = DummyMessage()

        unsubscribe_update = DummyUpdate(user_id)
        await telegram_bot.unsubscribe(unsubscribe_update, None)
        self.assertNotIn(user_id, memory.get_opted_in_users())

        subscribe_update = DummyUpdate(user_id)
        await telegram_bot.subscribe(subscribe_update, None)
        self.assertIn(user_id, memory.get_opted_in_users())


if __name__ == "__main__":
    unittest.main()
