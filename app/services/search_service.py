from __future__ import annotations

from app.core.logger import get_logger
from app.search.search_engine import SearchEngine, SearchResult
from app.storage.database import get_database_path

from .freshness_service import FreshnessService
from .pipeline_service import PipelineService


logger = get_logger(__name__)


class SearchService:
    def __init__(
        self,
        *,
        freshness_service: FreshnessService | None = None,
        pipeline_service: PipelineService | None = None,
        search_engine: SearchEngine | None = None,
    ) -> None:
        self.freshness = freshness_service or FreshnessService()
        self.pipeline = pipeline_service or PipelineService(self.freshness)
        self.search_engine = search_engine or SearchEngine(get_database_path())

    def search(self, query: str, user_id: int | None = None) -> list[SearchResult]:
        del user_id
        normalized = " ".join((query or "").strip().split())
        if not normalized:
            return []

        opportunity_results = self.search_engine.search_opportunities(normalized, limit=5)
        if opportunity_results:
            return opportunity_results

        fallback_results = self.search_engine.search_content(normalized, limit=5)
        if fallback_results:
            if len(fallback_results) < 2:
                return fallback_results
            strong_fallback = [
                item
                for item in fallback_results
                if (item.action_hint or "").strip() or (item.deadline_text or "").strip()
            ]
            return strong_fallback or fallback_results[:2]

        if self.freshness.is_search_data_stale():
            try:
                self.pipeline.refresh_if_needed(search=True, force=True)
            except Exception:
                logger.exception("SearchService: pipeline refresh failed; using current stored data")
            opportunity_results = self.search_engine.search_opportunities(normalized, limit=5)
            if opportunity_results:
                return opportunity_results
            fallback_results = self.search_engine.search_content(normalized, limit=5)
            if len(fallback_results) < 2:
                return fallback_results
            strong_fallback = [
                item
                for item in fallback_results
                if (item.action_hint or "").strip() or (item.deadline_text or "").strip()
            ]
            return strong_fallback or fallback_results[:2]

        return []
