"""Listing service for user-facing scrape and listing inspection."""

from decimal import Decimal

from sqlalchemy.orm import Session, sessionmaker

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
            scrape_service = ScrapeService(
                watch_repository=WatchRepository(session),
                source_repository=SourceRepository(session),
                listing_repository=ListingRepository(session),
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

            pending_count = len(ListingRepository(session).list_unnotified_for_watch(watch.id))
            result = ScrapeNowResult(
                watch_id=watch.id,
                sources_seen=len(sources),
                sources_scraped=scraped_count,
                sources_skipped=skipped_count,
                listings_created=created_count,
                pending_listings=pending_count,
                warnings=warnings,
            )
            session.commit()
            return result

    def list_watch_listings(
        self,
        discord_user_id: str,
        watch_id: int,
    ) -> list[DigestListing]:
        """List unnotified persisted listings for one owned watch."""

        with self.session_factory() as session:
            user = UserRepository(session).get_or_create_by_discord_id(discord_user_id)
            watch = WatchRepository(session).get_active_for_user(watch_id, user.id)
            if watch is None:
                raise WatchNotFoundError("watch not found")
            digest = DigestService(ListingRepository(session)).build_digest(watch)
            if digest is None:
                return []
            listings = list(digest.listings)
            session.commit()
            return listings
