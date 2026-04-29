"""Scheduled jobs and scheduler setup."""

from collections.abc import Awaitable, Callable
from decimal import Decimal

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import Session, sessionmaker

from car_watch_bot.config import Settings
from car_watch_bot.db.repositories import (
    ListingRepository,
    ScrapeAttemptRepository,
    SourceRepository,
    WatchRepository,
)
from car_watch_bot.scrapers.base import ScraperAdapter
from car_watch_bot.services.notification_service import NotificationService
from car_watch_bot.services.scrape_service import ScrapeService


async def collect_listings_job(
    session_factory: sessionmaker[Session],
    scraper_adapters: dict[str, ScraperAdapter],
    usd_to_aud_rate: Decimal,
) -> int:
    """Run scheduled mock scraping."""

    with session_factory() as session:
        scrape_service = ScrapeService(
            watch_repository=WatchRepository(session),
            source_repository=SourceRepository(session),
            listing_repository=ListingRepository(session),
            scrape_attempt_repository=ScrapeAttemptRepository(session),
            scraper_adapters=scraper_adapters,
            usd_to_aud_rate=usd_to_aud_rate,
        )
        created_count = await scrape_service.run_once()
        session.commit()
        return created_count


async def send_due_digests_job(notification_service: NotificationService) -> int:
    """Send due digest notifications."""

    return await notification_service.send_due_digests()


def create_scheduler(
    settings: Settings,
    scrape_job: Callable[[], Awaitable[int]],
    digest_job: Callable[[], Awaitable[int]],
) -> AsyncIOScheduler:
    """Create an APScheduler instance for bot jobs."""

    scheduler = AsyncIOScheduler(timezone=settings.default_timezone)
    scheduler.add_job(
        scrape_job,
        "interval",
        minutes=settings.scrape_interval_minutes,
        id="collect_listings",
        replace_existing=True,
    )
    scheduler.add_job(
        digest_job,
        "interval",
        minutes=1,
        id="send_due_digests",
        replace_existing=True,
    )
    return scheduler
