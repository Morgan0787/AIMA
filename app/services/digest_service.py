from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.logger import get_logger
from app.digest.digest_builder import DigestBuildResult, DigestBuilder

from .freshness_service import FreshnessService
from .pipeline_service import PipelineRefreshResult, PipelineService


logger = get_logger(__name__)


@dataclass
class DigestServiceResult:
    digest_text: str
    title: str
    items_count: int
    included_processed_message_ids: list[int]
    used_fallback: bool
    refreshed: bool
    refresh_result: PipelineRefreshResult | None
    status_snapshot: dict[str, Any]


class DigestService:
    def __init__(
        self,
        *,
        freshness_service: FreshnessService | None = None,
        pipeline_service: PipelineService | None = None,
    ) -> None:
        self.freshness = freshness_service or FreshnessService()
        self.pipeline = pipeline_service or PipelineService(self.freshness)

    def _build_digest(self) -> DigestBuildResult:
        return DigestBuilder().build()

    def _empty_fallback_text(self) -> str:
        return (
            "Сейчас сильный дайджест ещё не собрался.\n\n"
            "Я обновила pipeline и проверила базу, но уверенных свежих сигналов пока мало. "
            "Попробуй /top, /urgent или /find чуть позже."
        )

    def get_digest(self, force_refresh: bool = False) -> DigestServiceResult:
        try:
            refresh_result = self.pipeline.refresh_if_needed(digest=True, force=force_refresh)
        except Exception:
            logger.exception("DigestService: pipeline refresh failed; using current stored data")
            refresh_result = PipelineRefreshResult()
        result = self._build_digest()

        if not result.digest_text and not refresh_result.refreshed:
            logger.info("DigestService: digest empty after initial build, forcing one safe refresh")
            try:
                second_refresh = self.pipeline.refresh_if_needed(digest=True, force=True)
            except Exception:
                logger.exception("DigestService: forced refresh failed; using fallback digest behavior")
                second_refresh = PipelineRefreshResult()
            if second_refresh.refreshed:
                refresh_result = second_refresh
            result = self._build_digest()

        status_snapshot = self.freshness.get_status_snapshot().to_dict()
        if result.digest_text:
            return DigestServiceResult(
                digest_text=result.digest_text,
                title=result.title,
                items_count=result.items_count,
                included_processed_message_ids=list(result.included_processed_message_ids),
                used_fallback=not bool(result.included_processed_message_ids) and result.items_count > 0,
                refreshed=refresh_result.refreshed,
                refresh_result=refresh_result,
                status_snapshot=status_snapshot,
            )

        return DigestServiceResult(
            digest_text=self._empty_fallback_text(),
            title="",
            items_count=0,
            included_processed_message_ids=[],
            used_fallback=True,
            refreshed=refresh_result.refreshed,
            refresh_result=refresh_result,
            status_snapshot=status_snapshot,
        )
