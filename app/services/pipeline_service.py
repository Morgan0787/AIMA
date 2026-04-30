from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.analyzer.message_analyzer import AnalysisStats, MessageAnalyzer
from app.collector.telegram_collector import CollectionResult, TelegramCollector
from app.core.logger import get_logger
from app.opportunity.hunter import OpportunityBackfillStats, OpportunityHunter
from app.processor.message_processor import MessageProcessor, ProcessingStats
from app.storage.database import init_db

from .freshness_service import FreshnessService


logger = get_logger(__name__)


@dataclass
class PipelineRefreshResult:
    steps_run: list[str] = field(default_factory=list)
    refreshed: bool = False
    ingestion: CollectionResult | None = None
    processing: ProcessingStats | None = None
    analysis: AnalysisStats | None = None
    opportunities: OpportunityBackfillStats | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "steps_run": list(self.steps_run),
            "refreshed": self.refreshed,
            "ingestion": vars(self.ingestion) if self.ingestion else None,
            "processing": vars(self.processing) if self.processing else None,
            "analysis": vars(self.analysis) if self.analysis else None,
            "opportunities": vars(self.opportunities) if self.opportunities else None,
        }


class PipelineService:
    def __init__(self, freshness_service: FreshnessService | None = None) -> None:
        init_db()
        self.freshness = freshness_service or FreshnessService()

    def refresh_ingestion(self) -> CollectionResult:
        logger.info("PipelineService: refreshing ingestion")
        return TelegramCollector().collect_new_messages()

    def refresh_processing(self) -> ProcessingStats:
        logger.info("PipelineService: refreshing processing")
        return MessageProcessor().process()

    def refresh_analysis(self) -> AnalysisStats:
        logger.info("PipelineService: refreshing analysis")
        return MessageAnalyzer().analyze()

    def refresh_opportunities(self) -> OpportunityBackfillStats:
        logger.info("PipelineService: refreshing opportunities")
        return OpportunityHunter().backfill()

    def refresh_all(self) -> PipelineRefreshResult:
        result = PipelineRefreshResult()
        result.ingestion = self.refresh_ingestion()
        result.steps_run.append("ingestion")
        result.processing = self.refresh_processing()
        result.steps_run.append("processing")
        result.analysis = self.refresh_analysis()
        result.steps_run.append("analysis")
        result.opportunities = self.refresh_opportunities()
        result.steps_run.append("opportunities")
        result.refreshed = True
        return result

    def refresh_if_needed(
        self,
        *,
        digest: bool = False,
        opportunities: bool = False,
        search: bool = False,
        force: bool = False,
    ) -> PipelineRefreshResult:
        should_refresh = force
        if digest and self.freshness.is_digest_stale():
            should_refresh = True
        if opportunities and self.freshness.is_opportunity_data_stale():
            should_refresh = True
        if search and self.freshness.is_search_data_stale():
            should_refresh = True
        if not should_refresh:
            return PipelineRefreshResult()
        return self.refresh_all()
