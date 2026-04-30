"""
Main entrypoint for Jarvis v2 Core.

At this stage, the goal is to:
- Initialize configuration
- Set up logging
- Initialize the SQLite database
- Print a simple message so you know everything is wired correctly

Full business logic (Telegram collection, analysis, etc.) will be added
in later steps.
"""

from __future__ import annotations

import hashlib
import json
import re


def main() -> None:
    """
    Entry function for the Jarvis v2 Core application.
    """
    # Keep imports inside `main()` so `python -m app.main` works cleanly,
    # and to avoid accidental circular import issues as the project grows.
    from dotenv import load_dotenv

    # Place your real `.env` file in the project root (same folder as `config/`).
    load_dotenv()

    from .core.config import get_config
    from .core.logger import get_logger
    from .storage.database import init_db
    from .digest.digest_builder import DigestBuilder
    from .digest.publisher import publish_digest
    from .storage.repository import Repository
    from .opportunity.hunter import OpportunityHunter
    from .services import PipelineService

    logger = get_logger(__name__)

    logger.info(
        "Starting Jarvis v2 Core (Step 5: collection + processing + analysis + digest)."
    )

    # Load configuration to ensure settings.json is valid.
    config = get_config()
    logger.info("Loaded configuration. Database file: %s", config.database_path)

    # Initialize the SQLite database.
    init_db()

    pipeline = PipelineService()
    collection_result = pipeline.refresh_ingestion()

    logger.info(
        "Collection complete. Total new messages: %d",
        collection_result.total_new_messages,
    )

    processing_stats = pipeline.refresh_processing()

    logger.info(
        "Processing complete. Processed: %d, duplicates: %d",
        processing_stats.processed_count,
        processing_stats.duplicate_count,
    )

    analysis_stats = pipeline.refresh_analysis()

    logger.info(
        "Analysis complete. Analyzed: %d, failures: %d",
        analysis_stats.analyzed_count,
        analysis_stats.failed_count,
    )

    hunter = OpportunityHunter()
    opportunity_stats = pipeline.refresh_opportunities()
    opportunity_report = hunter.build_report()

    repo = Repository()
    builder = DigestBuilder()
    digest_result = builder.build()

    digest_published = "no"
    digest_items = digest_result.items_count

    if digest_items > 0:
        from datetime import UTC, datetime  # local import for simplicity

        now = datetime.now(UTC).replace(tzinfo=None)
        digest_date = now.date().isoformat()
        created_at = now.isoformat(timespec="seconds")

        min_publish_items = 3
        recent_used_days = 7
        similarity_threshold = 0.85
        debug_reuse_mode = bool(getattr(config.debug, "reuse_analyzed_messages", False))

        def _normalize_for_similarity(text: str) -> str:
            text = (text or "").lower()
            text = re.sub(r"[^\w\s]+", " ", text, flags=re.UNICODE)
            text = re.sub(r"\s+", " ", text).strip()
            return text

        def _text_similarity(a: str, b: str) -> float:
            a_words = set(_normalize_for_similarity(a).split())
            b_words = set(_normalize_for_similarity(b).split())
            if not a_words or not b_words:
                return 0.0
            inter = len(a_words & b_words)
            union = len(a_words | b_words)
            if union == 0:
                return 0.0
            return inter / union

        digest_hash = hashlib.sha256(
            (digest_result.digest_text or "").encode("utf-8")
        ).hexdigest()
        current_ids = set(digest_result.included_processed_message_ids)

        skip_reason: str | None = None
        similarity_to_last = 0.0

        if not current_ids and not debug_reuse_mode:
            skip_reason = "fallback_snapshot_only"
            logger.info("Skipping digest publish: built from fallback snapshot without new analyzed items.")

        if skip_reason is None and not debug_reuse_mode and digest_items < min_publish_items:
            skip_reason = "too_few_items"
            logger.info(
                "Skipping digest publish: too few items (%d < %d).",
                digest_items,
                min_publish_items,
            )

        if skip_reason is None and current_ids and not debug_reuse_mode:
            recent_used_ids = repo.get_recent_published_processed_message_ids(
                days=recent_used_days
            )
            if current_ids.issubset(recent_used_ids):
                skip_reason = "no_new_items"
                logger.info(
                    "Skipping digest publish: no new items (all used in last %d days).",
                    recent_used_days,
                )

        if skip_reason is None and not debug_reuse_mode:
            last_published = repo.get_last_published_digest()
            if last_published:
                last_text = str(last_published.get("content") or "")
                last_hash = hashlib.sha256(last_text.encode("utf-8")).hexdigest()
                similarity_to_last = _text_similarity(digest_result.digest_text, last_text)

                if digest_hash == last_hash or similarity_to_last >= similarity_threshold:
                    skip_reason = "too_similar_to_previous"
                    logger.info(
                        "Skipping digest publish: too similar to previous digest (similarity=%.2f).",
                        similarity_to_last,
                    )

        published = False
        published_to = None
        if debug_reuse_mode:
            logger.info("Debug reuse mode enabled: bypassing anti-repeat publish policy checks.")
        if skip_reason is None:
            published, published_to = publish_digest(
                digest_result.digest_text, title=digest_result.title
            )
            digest_published = "yes" if published else "no"
        else:
            digest_published = "no"

        metadata = {
            "published_processed_message_ids": digest_result.included_processed_message_ids,
            "published_at": created_at if skip_reason is None else None,
            "digest_hash": digest_hash,
            "publish_policy": {
                "min_publish_items": min_publish_items,
                "recent_used_days": recent_used_days,
                "similarity_threshold": similarity_threshold,
                "skip_reason": skip_reason,
                "similarity_to_last": round(similarity_to_last, 4),
            },
        }
        repo.insert_digest(
            digest_date=digest_date,
            title=digest_result.title,
            content=digest_result.digest_text,
            created_at=created_at,
            published_to=published_to,
            metadata_json=json.dumps(metadata, ensure_ascii=False),
        )

        # Mark as included only when digest passed policy checks.
        if skip_reason is None:
            repo.mark_processed_messages_included(digest_result.included_processed_message_ids)
    else:
        logger.info("No digest candidates matched thresholds; digest not created/published.")

    if getattr(config.opportunity, "enabled", True):
        if opportunity_report.items_count > 0:
            logger.info(
                "Opportunity report built: items=%d new_candidates=%d",
                opportunity_report.items_count,
                opportunity_stats.created_or_updated,
            )
            if getattr(config.opportunity, "publish_to_telegram", True) and opportunity_stats.created_or_updated > 0:
                opp_published, _ = publish_digest(opportunity_report.report_text, title=opportunity_report.title)
                logger.info("Opportunity report published to Telegram: %s", "yes" if opp_published else "no")
            else:
                logger.info("Opportunity report not published to Telegram (publish disabled or no new opportunities).")
        else:
            logger.info("Opportunity hunter enabled but report is empty.")

    print("=== Jarvis v2 Core Summary ===")
    print(f"New raw messages collected: {collection_result.total_new_messages}")
    print(f"Messages processed:        {processing_stats.processed_count}")
    print(f"Duplicates detected:       {processing_stats.duplicate_count}")
    print(f"Messages analyzed:         {analysis_stats.analyzed_count}")
    print(f"Analysis failures:         {analysis_stats.failed_count}")
    print(f"Digest items:              {digest_items}")
    print(f"Digest published:          {digest_published}")
    print(f"Active opportunities:      {opportunity_stats.active_count if 'opportunity_stats' in locals() else 0}")
    print("================================")


if __name__ == "__main__":
    main()
