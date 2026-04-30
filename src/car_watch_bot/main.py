"""Application entrypoint."""

import logging

from car_watch_bot.bot.client import DiscordDigestSender, create_bot_client
from car_watch_bot.config import get_settings
from car_watch_bot.db.database import (
    create_database_engine,
    create_session_factory,
    init_database,
)
from car_watch_bot.logging_config import configure_logging
from car_watch_bot.scheduler.jobs import (
    collect_listings_job,
    create_scheduler,
    send_due_digests_job,
)
from car_watch_bot.scrapers.autotempest import AutoTempestScraper
from car_watch_bot.scrapers.cars_on_line import CarsOnLineScraper
from car_watch_bot.scrapers.corvette_magazine import CorvetteMagazineScraper
from car_watch_bot.scrapers.diagnostic import DiagnosticScraper
from car_watch_bot.scrapers.mock import MockScraper
from car_watch_bot.scrapers.vettefinders import VetteFindersScraper
from car_watch_bot.services.listing_service import ListingService
from car_watch_bot.services.notification_service import NotificationService
from car_watch_bot.services.source_service import SourceService
from car_watch_bot.services.watch_service import WatchService


logger = logging.getLogger(__name__)
COMMAND_FORMAT_VERSION = "compact-v2"


def _scraper_adapters(settings):
    """Create scraper adapters for runtime use."""

    return {
        "mock": MockScraper(),
        "autotempest": AutoTempestScraper(
            user_agent=settings.scraper_user_agent,
            timeout_seconds=settings.scraper_timeout_seconds,
            min_interval_seconds=settings.scraper_min_interval_seconds,
        ),
        "cars_on_line": CarsOnLineScraper(
            user_agent=settings.scraper_user_agent,
            timeout_seconds=settings.scraper_timeout_seconds,
            min_interval_seconds=settings.scraper_min_interval_seconds,
        ),
        "corvette_magazine": CorvetteMagazineScraper(
            user_agent=settings.scraper_user_agent,
            timeout_seconds=settings.scraper_timeout_seconds,
            min_interval_seconds=settings.scraper_min_interval_seconds,
        ),
        "vettefinders": VetteFindersScraper(
            user_agent=settings.scraper_user_agent,
            timeout_seconds=settings.scraper_timeout_seconds,
            min_interval_seconds=settings.scraper_min_interval_seconds,
        ),
    }


def main() -> None:
    """Load configuration and run the Discord bot."""

    settings = get_settings()
    configure_logging(settings.log_level)
    engine = create_database_engine(settings.database_url)
    init_database(engine)
    session_factory = create_session_factory(engine)
    scraper_adapters = _scraper_adapters(settings)
    logger.info(
        "starting car watch bot command_format_version=%s scraper_adapters=%s",
        COMMAND_FORMAT_VERSION,
        ",".join(sorted(scraper_adapters)),
    )
    watch_service = WatchService(
        session_factory=session_factory,
        default_timezone=settings.default_timezone,
        default_currency=settings.default_currency,
        default_distance_unit=settings.default_distance_unit,
    )
    source_service = SourceService(
        session_factory=session_factory,
        source_test_scrapers=scraper_adapters,
        source_diagnostic_scraper=DiagnosticScraper(
            user_agent=settings.scraper_user_agent,
            timeout_seconds=settings.scraper_timeout_seconds,
            min_interval_seconds=settings.scraper_min_interval_seconds,
        ),
        allow_unregistered_sources=False,
    )
    listing_service = ListingService(
        session_factory=session_factory,
        scraper_adapters=scraper_adapters,
        usd_to_aud_rate=settings.usd_to_aud_rate,
    )
    client = create_bot_client(settings, watch_service, source_service, listing_service)
    notification_service = NotificationService(
        session_factory=session_factory,
        digest_sender=DiscordDigestSender(client),
    )

    async def scrape_job() -> int:
        """Run the scheduled scrape job."""

        return await collect_listings_job(
            session_factory=session_factory,
            scraper_adapters=_scraper_adapters(settings),
            usd_to_aud_rate=settings.usd_to_aud_rate,
        )

    async def digest_job() -> int:
        """Run the scheduled digest job."""

        return await send_due_digests_job(notification_service)

    scheduler = create_scheduler(
        settings=settings,
        scrape_job=scrape_job,
        digest_job=digest_job,
    )
    client.scheduler = scheduler
    if not settings.discord_bot_token:
        raise RuntimeError("DISCORD_BOT_TOKEN is required to run the bot")
    client.run(settings.discord_bot_token)


if __name__ == "__main__":
    main()
