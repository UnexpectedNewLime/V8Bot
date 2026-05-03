"""Listing service for user-facing scrape and listing inspection."""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session, sessionmaker

from car_watch_bot.core.listing_status import (
    LISTING_STATUS_SENT,
    USER_SETTABLE_LISTING_STATUSES,
)
from car_watch_bot.core.models import DigestListing, ScrapeNowResult
from car_watch_bot.db.repositories import (
    ListingRepository,
    ScrapeAttemptRepository,
    SourceRepository,
    UserRepository,
    WatchRepository,
)
from car_watch_bot.scrapers.base import ScraperAdapter
from car_watch_bot.services.digest_service import DigestService
from car_watch_bot.services.scrape_service import ScrapeService
from car_watch_bot.services.watch_service import WatchNotFoundError


class ListingServiceError(Exception):
    """Base exception for listing service failures."""


class ListingStatusValidationError(ListingServiceError):
    """Raised when a requested listing status is invalid."""


class WatchListingNotFoundError(ListingServiceError):
    """Raised when a listing is not attached to an owned watch."""


@dataclass(frozen=True)
class ListingStatusUpdateResult:
    """Result returned after a watch-listing status update."""

    watch_id: int
    listing_id: int
    status: str


class ListingService:
    """Business operations for listing inspection."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        scraper_adapters: dict[str, ScraperAdapter],
        usd_to_aud_rate: Decimal,
    ) -> None:
        self.session_factory = session_factory
        self.scraper_adapters = scraper_adapters
        self.usd_to_aud_rate = usd_to_aud_rate

    async def scrape_watch_now(
        self,
        discord_user_id: str,
        watch_id: int,
    ) -> ScrapeNowResult:
        """Run scraping immediately for one owned watch."""

        with self.session_factory() as session:
            user = UserRepository(session).get_or_create_by_discord_id(discord_user_id)
            watch = WatchRepository(session).get_active_for_user(watch_id, user.id)
            if watch is None:
                raise WatchNotFoundError("watch not found")

            sources = SourceRepository(session).list_sources_for_watch(watch.id)
            listing_repository = ListingRepository(session)
            before_pending_ids = {
                listing.id
                for listing in listing_repository.list_unnotified_for_watch(watch.id)
            }
            scrape_service = ScrapeService(
                watch_repository=WatchRepository(session),
                source_repository=SourceRepository(session),
                listing_repository=listing_repository,
                scrape_attempt_repository=ScrapeAttemptRepository(session),
                scraper_adapters=self.scraper_adapters,
                usd_to_aud_rate=self.usd_to_aud_rate,
            )
            created_count = 0
            scraped_count = 0
            skipped_count = 0
            warnings: list[str] = []
            for source in sources:
                adapter = self.scraper_adapters.get(source.kind)
                if adapter is None:
                    skipped_count += 1
                    warnings.append(f"source {source.id} skipped: no adapter for {source.kind}")
                    continue
                created_count += await scrape_service.scrape_watch_source(
                    watch=watch,
                    source=source,
                    adapter=adapter,
                )
                scraped_count += 1

            pending_listings = listing_repository.list_unnotified_for_watch(watch.id)
            new_listing_ids = [
                listing.id
                for listing in pending_listings
                if listing.id not in before_pending_ids
            ]
            result = ScrapeNowResult(
                watch_id=watch.id,
                sources_seen=len(sources),
                sources_scraped=scraped_count,
                sources_skipped=skipped_count,
                listings_created=created_count,
                pending_listings=len(pending_listings),
                warnings=warnings,
                new_listing_ids=new_listing_ids,
            )
            session.commit()
            return result

    def list_watch_listings(
        self,
        discord_user_id: str,
        watch_id: int,
        listing_ids: list[int] | None = None,
    ) -> list[DigestListing]:
        """List unnotified persisted listings for one owned watch."""

        with self.session_factory() as session:
            user = UserRepository(session).get_or_create_by_discord_id(discord_user_id)
            watch = WatchRepository(session).get_active_for_user(watch_id, user.id)
            if watch is None:
                raise WatchNotFoundError("watch not found")
            digest_service = DigestService(ListingRepository(session))
            if listing_ids is None:
                digest = digest_service.build_listing_history(watch)
            else:
                digest = digest_service.build_digest_for_listing_ids(watch, listing_ids)
            if digest is None:
                return []
            listings = list(digest.listings)
            session.commit()
            return listings

    def mark_watch_listings_sent(
        self,
        discord_user_id: str,
        watch_id: int,
        listing_ids: list[int],
    ) -> None:
        """Mark displayed watch listings as sent."""

        if not listing_ids:
            return
        with self.session_factory() as session:
            user = UserRepository(session).get_or_create_by_discord_id(discord_user_id)
            watch = WatchRepository(session).get_active_for_user(watch_id, user.id)
            if watch is None:
                raise WatchNotFoundError("watch not found")
            DigestService(ListingRepository(session)).mark_digest_sent(
                watch.id,
                listing_ids,
            )
            session.commit()

    def update_watch_listing_status(
        self,
        discord_user_id: str,
        watch_id: int,
        listing_id: int,
        status: str,
    ) -> ListingStatusUpdateResult:
        """Update one watch-listing status for an owning Discord user."""

        if status not in USER_SETTABLE_LISTING_STATUSES:
            raise ListingStatusValidationError("unsupported listing status")
        with self.session_factory() as session:
            user = UserRepository(session).get_or_create_by_discord_id(discord_user_id)
            watch = WatchRepository(session).get_active_for_user(watch_id, user.id)
            if watch is None:
                raise WatchNotFoundError("watch not found")
            listing_repository = ListingRepository(session)
            watch_listing = listing_repository.update_watch_listing_status_for_user(
                user_id=user.id,
                watch_id=watch.id,
                listing_id=listing_id,
                status=status,
            )
            if watch_listing is None:
                raise WatchListingNotFoundError("listing not found for watch")
            result = ListingStatusUpdateResult(
                watch_id=watch.id,
                listing_id=listing_id,
                status=watch_listing.status,
            )
            session.commit()
            return result

    def unstar_watch_listing(
        self,
        discord_user_id: str,
        watch_id: int,
        listing_id: int,
    ) -> ListingStatusUpdateResult:
        """Remove one watch listing from the starred shortlist."""

        with self.session_factory() as session:
            user = UserRepository(session).get_or_create_by_discord_id(discord_user_id)
            watch = WatchRepository(session).get_active_for_user(watch_id, user.id)
            if watch is None:
                raise WatchNotFoundError("watch not found")
            listing_repository = ListingRepository(session)
            watch_listing = listing_repository.update_watch_listing_status_for_user(
                user_id=user.id,
                watch_id=watch.id,
                listing_id=listing_id,
                status=LISTING_STATUS_SENT,
            )
            if watch_listing is None:
                raise WatchListingNotFoundError("listing not found for watch")
            result = ListingStatusUpdateResult(
                watch_id=watch.id,
                listing_id=listing_id,
                status=watch_listing.status,
            )
            session.commit()
            return result
