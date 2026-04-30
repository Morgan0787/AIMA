from __future__ import annotations

from dataclasses import dataclass

from app.core.logger import get_logger
from app.opportunity.hunter import OpportunityHunter, OpportunityReportResult
from app.search.search_engine import SearchEngine, SearchResult
from app.storage.database import get_database_path

from .freshness_service import FreshnessService
from .pipeline_service import PipelineService


logger = get_logger(__name__)


@dataclass
class OpportunityCollectionResult:
    report_text: str
    items_count: int
    new_items_count: int
    title: str
    refreshed: bool


class OpportunityService:
    def __init__(
        self,
        *,
        freshness_service: FreshnessService | None = None,
        pipeline_service: PipelineService | None = None,
        search_engine: SearchEngine | None = None,
    ) -> None:
        self.freshness = freshness_service or FreshnessService()
        self.pipeline = pipeline_service or PipelineService(self.freshness)
        self.search = search_engine or SearchEngine(get_database_path())

    def _refresh_if_needed(self, force_refresh: bool = False) -> bool:
        try:
            result = self.pipeline.refresh_if_needed(
                opportunities=True,
                search=True,
                force=force_refresh,
            )
        except Exception:
            logger.exception("OpportunityService: pipeline refresh failed; using current stored data")
            return False
        return result.refreshed

    def get_opportunities(self, force_refresh: bool = False) -> OpportunityCollectionResult:
        report: OpportunityReportResult = OpportunityHunter().build_report()
        refreshed = False
        should_refresh = force_refresh or (
            not report.report_text and self.freshness.is_opportunity_data_stale()
        )
        if should_refresh:
            refreshed = self._refresh_if_needed(force_refresh=True)
            report = OpportunityHunter().build_report()
        return OpportunityCollectionResult(
            report_text=report.report_text,
            items_count=report.items_count,
            new_items_count=report.new_items_count,
            title=report.title,
            refreshed=refreshed,
        )

    def get_urgent(self, force_refresh: bool = False, limit: int = 5) -> list[SearchResult]:
        results = self.search.get_urgent_opportunities(limit=limit)
        if force_refresh or (not results and self.freshness.is_opportunity_data_stale()):
            self._refresh_if_needed(force_refresh=True)
            results = self.search.get_urgent_opportunities(limit=limit)
        return results

    def get_top(self, force_refresh: bool = False, limit: int = 5) -> list[SearchResult]:
        results = self.search.get_top_opportunities(limit=limit)
        if force_refresh or (not results and self.freshness.is_opportunity_data_stale()):
            self._refresh_if_needed(force_refresh=True)
            results = self.search.get_top_opportunities(limit=limit)
        return results

    def get_deadlines(self, days: int = 7, force_refresh: bool = False, limit: int = 5) -> list[SearchResult]:
        results = self.search.get_upcoming_deadlines(days_ahead=days, limit=limit)
        if force_refresh or (not results and self.freshness.is_opportunity_data_stale()):
            self._refresh_if_needed(force_refresh=True)
            results = self.search.get_upcoming_deadlines(days_ahead=days, limit=limit)
        return results
