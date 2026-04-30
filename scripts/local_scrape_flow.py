"""Run the watch/source/scrape/list flow locally without Discord."""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from car_watch_bot.config import get_settings  # noqa: E402
from car_watch_bot.db.database import (  # noqa: E402
    create_database_engine,
    create_session_factory,
    init_database,
)
from car_watch_bot.main import _scraper_adapters  # noqa: E402
from car_watch_bot.scrapers.diagnostic import DiagnosticScraper  # noqa: E402
from car_watch_bot.services.listing_service import ListingService  # noqa: E402
from car_watch_bot.services.source_service import SourceService  # noqa: E402
from car_watch_bot.services.watch_service import WatchService  # noqa: E402


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description="Create or reuse a watch, add/test a source, scrape, and print listings.",
    )
    parser.add_argument("--discord-user-id", default="local-cli")
    parser.add_argument("--watch-id", type=int)
    parser.add_argument("--car-query", default="C5 Corvette")
    parser.add_argument("--keywords", default="manual")
    parser.add_argument("--exclude-keywords", default="")
    parser.add_argument("--notify-time", default="09:00")
    parser.add_argument("--source-name", default="AutoTempest Local")
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--no-scrape", action="store_true")
    return parser.parse_args()


async def main() -> None:
    """Run the local scrape flow."""

    args = parse_args()
    settings = get_settings()
    engine = create_database_engine(settings.database_url)
    init_database(engine)
    session_factory = create_session_factory(engine)
    adapters = _scraper_adapters(settings)
    watch_service = WatchService(
        session_factory=session_factory,
        default_timezone=settings.default_timezone,
        default_currency=settings.default_currency,
        default_distance_unit=settings.default_distance_unit,
    )
    source_service = SourceService(
        session_factory=session_factory,
        source_test_scrapers=adapters,
        source_diagnostic_scraper=DiagnosticScraper(
            user_agent=settings.scraper_user_agent,
            timeout_seconds=settings.scraper_timeout_seconds,
            min_interval_seconds=settings.scraper_min_interval_seconds,
        ),
        allow_unregistered_sources=False,
    )
    listing_service = ListingService(
        session_factory=session_factory,
        scraper_adapters=adapters,
        usd_to_aud_rate=settings.usd_to_aud_rate,
    )

    watch_id = args.watch_id
    payload: dict[str, Any] = {"discord_user_id": args.discord_user_id}
    if watch_id is None:
        watch = watch_service.create_watch(
            discord_user_id=args.discord_user_id,
            car_query=args.car_query,
            keywords=args.keywords,
            exclude_keywords=args.exclude_keywords,
            notify_time=args.notify_time,
        )
        watch_id = watch.watch_id
        payload["watch"] = watch.__dict__
    else:
        payload["watch_id"] = watch_id

    source_result = await source_service.add_source_to_watch(
        discord_user_id=args.discord_user_id,
        watch_id=watch_id,
        name=args.source_name,
        url=args.source_url,
    )
    payload["source"] = source_result.source.__dict__
    payload["source_test"] = source_result.source_test.__dict__

    if not args.no_scrape:
        scrape_result = await listing_service.scrape_watch_now(
            args.discord_user_id,
            watch_id,
        )
        payload["scrape_now"] = scrape_result.__dict__

    listings = listing_service.list_watch_listings(args.discord_user_id, watch_id)
    payload["pending_listing_count"] = len(listings)
    payload["pending_listings"] = [
        listing.__dict__ for listing in listings[: args.limit]
    ]
    print(json.dumps(payload, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
