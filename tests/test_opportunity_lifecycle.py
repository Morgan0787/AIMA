from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.digest.digest_builder import DigestBuilder
from app.opportunity.lifecycle import parse_deadline_date
from app.search.search_engine import SearchEngine
from app.storage.repository import Repository


def _setup_opportunity_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        cur = conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE,
                last_message_id INTEGER,
                username TEXT,
                title TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS raw_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id INTEGER NOT NULL,
                telegram_message_id INTEGER NOT NULL,
                post_link TEXT,
                message_text TEXT NOT NULL,
                message_date TEXT NOT NULL,
                collected_at TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                is_processed INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS processed_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                raw_message_id INTEGER NOT NULL UNIQUE,
                cleaned_text TEXT NOT NULL,
                short_text TEXT NOT NULL,
                is_duplicate INTEGER NOT NULL DEFAULT 0,
                duplicate_of_raw_message_id INTEGER,
                created_at TEXT NOT NULL,
                classification TEXT,
                importance_score REAL,
                metadata_json TEXT,
                processed_at TEXT NOT NULL,
                included_in_digest INTEGER NOT NULL DEFAULT 0,
                analysis_status TEXT NOT NULL DEFAULT 'pending',
                analysis_attempts INTEGER NOT NULL DEFAULT 0,
                analysis_last_attempt_at TEXT,
                analysis_error TEXT,
                analysis_provider TEXT
            );

            CREATE TABLE IF NOT EXISTS opportunities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                processed_message_id INTEGER NOT NULL UNIQUE,
                raw_message_id INTEGER NOT NULL,
                opportunity_type TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                channel_username TEXT,
                post_link TEXT,
                message_date TEXT,
                deadline_text TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                score REAL NOT NULL DEFAULT 0,
                confidence_score REAL NOT NULL DEFAULT 0,
                source_category TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata_json TEXT
            );

            CREATE TABLE IF NOT EXISTS digests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                digest_date TEXT NOT NULL,
                title TEXT,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                published_to TEXT,
                metadata_json TEXT
            );
            """
        )

        now = datetime.now(UTC).replace(microsecond=0)
        stale_dt = now - timedelta(days=60)
        fresh_dt = now - timedelta(days=2)
        fresh_deadline = (now + timedelta(days=5)).date().isoformat()

        rows = [
            (
                1,
                1,
                "grant",
                "Fresh grant call",
                "Fresh grant call for climate founders",
                "opportunities",
                "https://t.me/opportunities/1",
                fresh_dt.isoformat(),
                fresh_deadline,
                "active",
                8.5,
                0.92,
                "grant",
                fresh_dt.isoformat(),
                fresh_dt.isoformat(),
                '{"category": "grant", "deadline_text": "%s", "confidence_score": 0.92}' % fresh_deadline,
            ),
            (
                2,
                2,
                "event",
                "Old meetup",
                "Old meetup with no deadline",
                "community",
                "https://t.me/community/2",
                stale_dt.isoformat(),
                "",
                "active",
                6.5,
                0.45,
                "event",
                stale_dt.isoformat(),
                stale_dt.isoformat(),
                '{"category": "event", "confidence_score": 0.45}',
            ),
            (
                3,
                3,
                "hackathon",
                "Expired hackathon",
                "Expired hackathon with closed deadline",
                "hackathons",
                "https://t.me/hackathons/3",
                stale_dt.isoformat(),
                (now - timedelta(days=10)).date().isoformat(),
                "active",
                7.5,
                0.8,
                "hackathon",
                stale_dt.isoformat(),
                stale_dt.isoformat(),
                '{"category": "hackathon", "deadline_text": "%s", "confidence_score": 0.8}' % (now - timedelta(days=10)).date().isoformat(),
            ),
        ]

        cur.executemany(
            """
            INSERT INTO opportunities (
                processed_message_id, raw_message_id, opportunity_type, title, summary,
                channel_username, post_link, message_date, deadline_text, status, score,
                confidence_score, source_category, created_at, updated_at, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            rows,
        )
        conn.commit()
    finally:
        conn.close()


class OpportunityLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "opportunities.db"
        _setup_opportunity_db(self.db_path)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_repository_and_search_surfaces_skip_stale_opportunities(self) -> None:
        with patch("app.storage.database.get_database_path", return_value=self.db_path):
            repo = Repository()
            live_rows = repo.get_active_opportunities(limit=10, max_age_days=90, min_score=1)
            self.assertEqual([row["id"] for row in live_rows], [1])

        search_engine = SearchEngine(self.db_path)
        expected_summary = ["Fresh grant call for climate founders"]
        self.assertEqual([item.summary for item in search_engine.get_top_opportunities(limit=5)], expected_summary)
        self.assertEqual([item.summary for item in search_engine.get_urgent_opportunities(limit=5)], expected_summary)
        self.assertEqual([item.summary for item in search_engine.get_upcoming_deadlines(days_ahead=7, limit=5)], expected_summary)

        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.cursor()
            cur.execute("SELECT status FROM opportunities WHERE id = 2;")
            self.assertEqual(cur.fetchone()[0], "inactive")
            cur.execute("SELECT status FROM opportunities WHERE id = 3;")
            self.assertEqual(cur.fetchone()[0], "expired")
        finally:
            conn.close()

    def test_parse_deadline_date_rejects_ongoing_phrases(self) -> None:
        self.assertIsNone(parse_deadline_date("24/7"))

    def test_digest_fallback_uses_live_opportunities_only(self) -> None:
        config = SimpleNamespace(
            digest_max_age_days=3,
            debug=SimpleNamespace(reuse_analyzed_messages=False),
            opportunity=SimpleNamespace(max_age_days=90, min_score=4),
        )

        with patch("app.storage.database.get_database_path", return_value=self.db_path), patch(
            "app.digest.digest_builder.get_config", return_value=config
        ):
            builder = DigestBuilder(max_items=10, candidate_limit=10)
            result = builder.build()

        self.assertIn("Fresh grant call", result.digest_text)
        self.assertNotIn("Old meetup", result.digest_text)
        self.assertNotIn("Expired hackathon", result.digest_text)


if __name__ == "__main__":
    unittest.main()
