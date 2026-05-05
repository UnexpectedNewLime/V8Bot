"""Watch health diagnostics service."""

from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse

from sqlalchemy.orm import Session, sessionmaker

from car_watch_bot.db.models import ScrapeAttempt, SourceTestAttempt, WatchSource
from car_watch_bot.db.repositories import (
    ListingRepository,
    ScrapeAttemptRepository,
    SourceRepository,
    SourceTestAttemptRepository,
    UserRepository,
    WatchRepository,
)
from car_watch_bot.services.watch_service import WatchNotFoundError


@dataclass(frozen=True)
class ListingStatusCounts:
    """Watch-listing status counts safe for interface presentation."""

    pending_digest: int
    sent: int
    excluded: int
    other: int
    total: int
    other_statuses: dict[str, int]


@dataclass(frozen=True)
class ScrapeAttemptSummary:
    """Compact scrape attempt diagnostics."""

    attempt_id: int
    source_id: int
    source_name: str | None
    adapter_kind: str
    status: str
    finished_at: datetime | None
    listings_seen: int
    listings_matched: int
    listings_created: int
    error_message: str | None


@dataclass(frozen=True)
class SourceHealthSummary:
    """Compact source diagnostics for one watch source."""

    source_id: int
    name: str
    kind: str
    domain: str
    is_enabled: bool
    is_active: bool
    skipped_reason: str | None
    last_test_status: str | None
    last_test_finished_at: datetime | None
    last_test_notes: list[str]
    last_test_error: str | None


@dataclass(frozen=True)
class WatchHealthSummary:
    """Diagnostics summary for an owned watch."""

    watch_id: int
    watch_name: str
    watch_query: str
    is_active: bool
    notify_time: str
    timezone: str
    channel_id: str | None
    thread_id: str | None
    last_digest_sent_at: datetime | None
    source_count: int
    active_source_count: int
    skipped_source_count: int
    disabled_source_count: int
    inactive_source_count: int
    no_adapter_source_count: int
    listing_counts: ListingStatusCounts
    last_scrape: ScrapeAttemptSummary | None
    last_success: ScrapeAttemptSummary | None
    last_failure: ScrapeAttemptSummary | None
    recent_scrape_attempts: int
    recent_listings_seen: int
    recent_listings_matched: int
    recent_listings_created: int
    sources: list[SourceHealthSummary]


class WatchHealthService:
    """Read-only business operations for watch diagnostics."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        registered_source_kinds: set[str] | None = None,
        recent_scrape_limit: int = 10,
    ) -> None:
        self.session_factory = session_factory
        self.registered_source_kinds = registered_source_kinds
        self.recent_scrape_limit = recent_scrape_limit

    def get_watch_health(
        self,
        discord_user_id: str,
        watch_id: int,
    ) -> WatchHealthSummary:
        """Return health diagnostics for an active watch owned by a Discord user."""

        with self.session_factory() as session:
            user = UserRepository(session).get_or_create_by_discord_id(discord_user_id)
            watch = WatchRepository(session).get_active_for_user(watch_id, user.id)
            if watch is None:
                raise WatchNotFoundError("watch not found")

            source_repository = SourceRepository(session)
            watch_source_links = source_repository.list_watch_source_links(watch.id)
            source_ids = [link.source_id for link in watch_source_links]
            source_tests = SourceTestAttemptRepository(session).latest_for_sources(
                user.id,
                source_ids,
            )
            source_summaries = [
                self._source_summary(link, source_tests.get(link.source_id))
                for link in watch_source_links
            ]

            scrape_repository = ScrapeAttemptRepository(session)
            recent_attempts = scrape_repository.list_recent_for_watch(
                watch.id,
                limit=self.recent_scrape_limit,
            )
            source_names = {
                link.source_id: link.source.name for link in watch_source_links
            }
            listing_counts = _listing_status_counts(
                ListingRepository(session).count_statuses_for_watch(watch.id)
            )
            summary = WatchHealthSummary(
                watch_id=watch.id,
                watch_name=watch.name,
                watch_query=watch.query,
                is_active=watch.is_active,
                notify_time=watch.notification_time.strftime("%H:%M"),
                timezone=watch.timezone,
                channel_id=watch.channel_id,
                thread_id=watch.thread_id,
                last_digest_sent_at=watch.last_digest_sent_at,
                source_count=len(source_summaries),
                active_source_count=sum(
                    1
                    for source in source_summaries
                    if source.is_enabled and source.is_active
                ),
                skipped_source_count=sum(
                    1
                    for source in source_summaries
                    if source.skipped_reason is not None
                ),
                disabled_source_count=sum(
                    1 for source in source_summaries if not source.is_enabled
                ),
                inactive_source_count=sum(
                    1
                    for source in source_summaries
                    if source.is_enabled and not source.is_active
                ),
                no_adapter_source_count=sum(
                    1
                    for source in source_summaries
                    if source.skipped_reason is not None
                    and source.skipped_reason.startswith("no adapter")
                ),
                listing_counts=listing_counts,
                last_scrape=self._scrape_summary(
                    scrape_repository.get_latest_for_watch(watch.id),
                    source_names,
                ),
                last_success=self._scrape_summary(
                    scrape_repository.get_latest_for_watch(watch.id, status="success"),
                    source_names,
                ),
                last_failure=self._scrape_summary(
                    scrape_repository.get_latest_for_watch(watch.id, status="failed"),
                    source_names,
                ),
                recent_scrape_attempts=len(recent_attempts),
                recent_listings_seen=sum(
                    attempt.listings_seen for attempt in recent_attempts
                ),
                recent_listings_matched=sum(
                    attempt.listings_matched for attempt in recent_attempts
                ),
                recent_listings_created=sum(
                    attempt.listings_created for attempt in recent_attempts
                ),
                sources=source_summaries,
            )
            session.commit()
            return summary

    def _source_summary(
        self,
        watch_source: WatchSource,
        source_test: SourceTestAttempt | None,
    ) -> SourceHealthSummary:
        """Create diagnostics for one watch-source link."""

        source = watch_source.source
        return SourceHealthSummary(
            source_id=source.id,
            name=source.name,
            kind=source.kind,
            domain=_domain_for_url(source.base_url),
            is_enabled=watch_source.is_enabled,
            is_active=source.is_active,
            skipped_reason=self._skipped_reason(watch_source),
            last_test_status=source_test.status if source_test is not None else None,
            last_test_finished_at=(
                source_test.finished_at if source_test is not None else None
            ),
            last_test_notes=list(source_test.notes) if source_test is not None else [],
            last_test_error=(
                source_test.error_message if source_test is not None else None
            ),
        )

    def _skipped_reason(self, watch_source: WatchSource) -> str | None:
        """Return why a source would be skipped by runtime scraping."""

        source = watch_source.source
        if not watch_source.is_enabled:
            return "disabled for watch"
        if not source.is_active:
            return "source inactive"
        if (
            self.registered_source_kinds is not None
            and source.kind not in self.registered_source_kinds
        ):
            return f"no adapter for {source.kind}"
        return None

    def _scrape_summary(
        self,
        attempt: ScrapeAttempt | None,
        source_names: dict[int, str],
    ) -> ScrapeAttemptSummary | None:
        """Create scrape diagnostics for one attempt."""

        if attempt is None:
            return None
        return ScrapeAttemptSummary(
            attempt_id=attempt.id,
            source_id=attempt.source_id,
            source_name=source_names.get(attempt.source_id),
            adapter_kind=attempt.adapter_kind,
            status=attempt.status,
            finished_at=attempt.finished_at or attempt.started_at,
            listings_seen=attempt.listings_seen,
            listings_matched=attempt.listings_matched,
            listings_created=attempt.listings_created,
            error_message=attempt.error_message,
        )


def _listing_status_counts(status_counts: dict[str, int]) -> ListingStatusCounts:
    """Normalize raw status counts into explicit diagnostics fields."""

    pending_digest = status_counts.get("pending_digest", 0)
    sent = status_counts.get("sent", 0)
    excluded = status_counts.get("excluded", 0)
    known_total = pending_digest + sent + excluded
    total = sum(status_counts.values())
    other_statuses = {
        status: count
        for status, count in status_counts.items()
        if status not in {"pending_digest", "sent", "excluded"}
    }
    return ListingStatusCounts(
        pending_digest=pending_digest,
        sent=sent,
        excluded=excluded,
        other=total - known_total,
        total=total,
        other_statuses=other_statuses,
    )


def _domain_for_url(url: str | None) -> str:
    """Return a compact domain label for a source URL."""

    if not url:
        return "no url"
    host = urlparse(url).netloc.casefold().split("@")[-1].split(":")[0]
    return host.removeprefix("www.") or "unknown domain"
