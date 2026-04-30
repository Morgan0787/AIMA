
from __future__ import annotations

import sqlite3
from app.core.config import get_config


class UserMemory:
    def __init__(self) -> None:
        self.db = get_config().database_path
        self._init_tables()

    def _connect(self):
        return sqlite3.connect(self.db)

    def _init_tables(self) -> None:
        conn = self._connect()
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS saved_searches (
                user_id INTEGER NOT NULL,
                query TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, query)
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_interests (
                user_id INTEGER NOT NULL,
                interest TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, interest)
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_state (
                user_id INTEGER PRIMARY KEY,
                last_query TEXT,
                last_filter TEXT,
                last_deadline_days INTEGER,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        conn.close()

    def save_search(self, user_id: int, query: str) -> None:
        query = (query or "").strip()
        if not query:
            return
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            "INSERT OR IGNORE INTO saved_searches (user_id, query) VALUES (?, ?)",
            (user_id, query),
        )
        conn.commit()
        conn.close()

    def get_saved_searches(self, user_id: int) -> list[str]:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT query FROM saved_searches WHERE user_id=? ORDER BY created_at DESC, query ASC",
            (user_id,),
        )
        rows = cur.fetchall()
        conn.close()
        return [r[0] for r in rows]

    def delete_search(self, user_id: int, query: str) -> None:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM saved_searches WHERE user_id=? AND query=?",
            (user_id, (query or "").strip()),
        )
        conn.commit()
        conn.close()

    def get_interests(self, user_id: int) -> list[str]:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT interest FROM user_interests WHERE user_id=? ORDER BY created_at DESC, interest ASC",
            (user_id,),
        )
        rows = cur.fetchall()
        conn.close()
        return [r[0] for r in rows]

    def set_interests(self, user_id: int, interests: list[str]) -> None:
        cleaned = []
        seen = set()
        for item in interests:
            val = (item or "").strip().lower()
            if val and val not in seen:
                cleaned.append(val)
                seen.add(val)
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("DELETE FROM user_interests WHERE user_id=?", (user_id,))
        for val in cleaned:
            cur.execute(
                "INSERT OR IGNORE INTO user_interests (user_id, interest) VALUES (?, ?)",
                (user_id, val),
            )
        conn.commit()
        conn.close()

    def clear_interests(self, user_id: int) -> None:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("DELETE FROM user_interests WHERE user_id=?", (user_id,))
        conn.commit()
        conn.close()

    def set_last_query(self, user_id: int, query: str) -> None:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO user_state (user_id, last_query, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                last_query=excluded.last_query,
                updated_at=CURRENT_TIMESTAMP
            """,
            (user_id, (query or "").strip()),
        )
        conn.commit()
        conn.close()

    def get_last_query(self, user_id: int) -> str | None:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("SELECT last_query FROM user_state WHERE user_id=?", (user_id,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        return row[0]

    def set_last_deadline_days(self, user_id: int, days: int) -> None:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO user_state (user_id, last_deadline_days, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                last_deadline_days=excluded.last_deadline_days,
                updated_at=CURRENT_TIMESTAMP
            """,
            (user_id, int(days)),
        )
        conn.commit()
        conn.close()

    def get_last_deadline_days(self, user_id: int) -> int | None:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("SELECT last_deadline_days FROM user_state WHERE user_id=?", (user_id,))
        row = cur.fetchone()
        conn.close()
        return row[0] if row else None
