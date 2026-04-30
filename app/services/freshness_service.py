from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.config import get_config
from app.storage.database import get_database_path, init_db


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat(timespec="seconds")


@dataclass(frozen=True)
class FreshnessSnapshot:
    raw_count: int
    unprocessed_raw_count: int
    unanalyzed_processed_count: int
    active_opportunity_count: int
    digest_count: int
    last_ingestion_at: datetime | None
    last_processed_at: datetime | None
    last_analysis_source_at: datetime | None
    last_opportunity_update_at: datetime | None
    last_digest_at: datetime | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_count": self.raw_count,
            "unprocessed_raw_count": self.unprocessed_raw_count,
            "unanalyzed_processed_count": self.unanalyzed_processed_count,
            "active_opportunity_count": self.active_opportunity_count,
            "digest_count": self.digest_count,
            "last_ingestion_at": _to_iso(self.last_ingestion_at),
            "last_processed_at": _to_iso(self.last_processed_at),
            "last_analysis_source_at": _to_iso(self.last_analysis_source_at),
            "last_opportunity_update_at": _to_iso(self.last_opportunity_update_at),
            "last_digest_at": _to_iso(self.last_digest_at),
        }


class FreshnessService:
    def __init__(
        self,
        *,
        digest_ttl_hours: int = 12,
        opportunity_ttl_hours: int = 6,
        search_ttl_hours: int = 6,
    ) -> None:
        self.config = get_config()
        self.db_path = get_database_path()
        self.digest_ttl = timedelta(hours=max(1, digest_ttl_hours))
        self.opportunity_ttl = timedelta(hours=max(1, opportunity_ttl_hours))
        self.search_ttl = timedelta(hours=max(1, search_ttl_hours))
        init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_status_snapshot(self) -> FreshnessSnapshot:
        conn = self._connect()
        try:
            cur = conn.cursor()

            def scalar(query: str) -> Any:
                cur.execute(query)
                row = cur.fetchone()
                if row is None:
                    return None
                return row[0]

            raw_count = int(scalar("SELECT COUNT(*) FROM raw_messages;") or 0)
            unprocessed_raw_count = int(
                scalar("SELECT COUNT(*) FROM raw_messages WHERE is_processed = 0;") or 0
            )
            unanalyzed_processed_count = int(
                scalar(
                    """
                    SELECT COUNT(*)
                    FROM processed_messages
                    WHERE classification IS NULL;
                    """
                )
                or 0
            )
            active_opportunity_count = int(
                scalar("SELECT COUNT(*) FROM opportunities WHERE status = 'active';") or 0
            )
            digest_count = int(scalar("SELECT COUNT(*) FROM digests;") or 0)

            last_ingestion_at = _parse_iso(
                scalar("SELECT MAX(collected_at) FROM raw_messages;")
            )
            last_processed_at = _parse_iso(
                scalar("SELECT MAX(processed_at) FROM processed_messages;")
            )
            last_analysis_source_at = _parse_iso(
                scalar(
                    """
                    SELECT MAX(rm.message_date)
                    FROM processed_messages pm
                    JOIN raw_messages rm ON rm.id = pm.raw_message_id
                    WHERE pm.classification IS NOT NULL
                      AND pm.metadata_json IS NOT NULL
                      AND TRIM(pm.metadata_json) != '';
                    """
                )
            )
            last_opportunity_update_at = _parse_iso(
                scalar("SELECT MAX(updated_at) FROM opportunities;")
            )
            last_digest_at = _parse_iso(scalar("SELECT MAX(created_at) FROM digests;"))

            return FreshnessSnapshot(
                raw_count=raw_count,
                unprocessed_raw_count=unprocessed_raw_count,
                unanalyzed_processed_count=unanalyzed_processed_count,
                active_opportunity_count=active_opportunity_count,
                digest_count=digest_count,
                last_ingestion_at=last_ingestion_at,
                last_processed_at=last_processed_at,
                last_analysis_source_at=last_analysis_source_at,
                last_opportunity_update_at=last_opportunity_update_at,
                last_digest_at=last_digest_at,
            )
        finally:
            conn.close()

    def is_digest_stale(self) -> bool:
        snapshot = self.get_status_snapshot()
        if snapshot.digest_count == 0 or snapshot.last_digest_at is None:
            return True
        now = datetime.now(UTC)
        if now - snapshot.last_digest_at >= self.digest_ttl:
            return True
        if snapshot.last_analysis_source_at and snapshot.last_analysis_source_at > snapshot.last_digest_at:
            return True
        if snapshot.last_opportunity_update_at and snapshot.last_opportunity_update_at > snapshot.last_digest_at:
            return True
        return False

    def is_opportunity_data_stale(self) -> bool:
        snapshot = self.get_status_snapshot()
        if snapshot.active_opportunity_count == 0:
            return True
        if snapshot.unprocessed_raw_count > 0 or snapshot.unanalyzed_processed_count > 0:
            return True
        if snapshot.last_opportunity_update_at is None:
            return True
        now = datetime.now(UTC)
        if now - snapshot.last_opportunity_update_at >= self.opportunity_ttl:
            return True
        if (
            snapshot.last_analysis_source_at
            and snapshot.last_analysis_source_at > snapshot.last_opportunity_update_at
        ):
            return True
        return False

    def is_search_data_stale(self) -> bool:
        snapshot = self.get_status_snapshot()
        if snapshot.active_opportunity_count == 0:
            return True
        if snapshot.last_opportunity_update_at is None:
            return True
        now = datetime.now(UTC)
        if now - snapshot.last_opportunity_update_at >= self.search_ttl:
            return True
        if snapshot.unprocessed_raw_count > 0 or snapshot.unanalyzed_processed_count > 0:
            return True
        return False
