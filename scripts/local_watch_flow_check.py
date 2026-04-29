"""Run a local watch flow check through the service layer."""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from car_watch_bot.config import get_settings  # noqa: E402
from car_watch_bot.db.database import (  # noqa: E402
    create_database_engine,
    create_session_factory,
    init_database,
)
from car_watch_bot.db.models import Listing, User, Watch, WatchListing  # noqa: E402
from car_watch_bot.scrapers.autotempest import AutoTempestScraper  # noqa: E402
from car_watch_bot.scrapers.mock import MockScraper  # noqa: E402
from car_watch_bot.services.listing_service import ListingService  # noqa: E402
from car_watch_bot.services.source_service import SourceService  # noqa: E402


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description="Exercise watch scrape/listing services without Discord.",
    )
    parser.add_argument("--watch-id", type=int, default=1)
    parser.add_argument("--discord-user-id")
    parser.add_argument("--test-url")
    return parser.parse_args()


async def main() -> None:
    """Run the local flow check."""

    args = parse_args()
    settings = get_settings()
    engine = create_database_engine(settings.database_url)
    init_database(engine)
    session_factory = create_session_factory(engine)
    adapters = {
        "mock": MockScraper(),
        "autotempest": AutoTempestScraper(
            user_agent=settings.scraper_user_agent,
            timeout_seconds=settings.scraper_timeout_seconds,
            min_interval_seconds=settings.scraper_min_interval_seconds,
        ),
    }
    discord_user_id = args.discord_user_id or _discord_user_id_for_watch(
        session_factory,
        args.watch_id,
    )
    source_service = SourceService(
        session_factory=session_factory,
        source_test_scrapers=adapters,
    )
    listing_service = ListingService(
        session_factory=session_factory,
        scraper_adapters=adapters,
        usd_to_aud_rate=settings.usd_to_aud_rate,
    )

    payload: dict[str, Any] = {
        "watch_id": args.watch_id,
        "discord_user_id": discord_user_id,
    }
    if args.test_url:
        source_test = await source_service.test_source_url(discord_user_id, args.test_url)
        payload["source_test"] = source_test.__dict__

    scrape_result = await listing_service.scrape_watch_now(discord_user_id, args.watch_id)
    listings = listing_service.list_watch_listings(discord_user_id, args.watch_id)
    payload["scrape_now"] = scrape_result.__dict__
    payload["pending_listings"] = [listing.__dict__ for listing in listings]
    payload["suspicious_autotempest_search_listings"] = _suspicious_listings(
        session_factory,
        args.watch_id,
    )
    print(json.dumps(payload, indent=2, default=str))


def _discord_user_id_for_watch(session_factory, watch_id: int) -> str:
    """Find the Discord owner for a watch."""

    with session_factory() as session:
        row = session.execute(
            select(User.discord_user_id)
            .join(Watch, Watch.user_id == User.id)
            .where(Watch.id == watch_id)
        ).first()
    if row is None:
        raise ValueError(f"watch {watch_id} not found")
    return str(row[0])


def _suspicious_listings(session_factory, watch_id: int) -> list[dict[str, Any]]:
    """Return stored AutoTempest search URLs that should not be treated as listings."""

    with session_factory() as session:
        rows = session.execute(
            select(Listing.id, Listing.title, Listing.url)
            .join(WatchListing, WatchListing.listing_id == Listing.id)
            .where(WatchListing.watch_id == watch_id)
            .where(Listing.url.like("https://www.autotempest.com/results%"))
        ).all()
    return [
        {
            "listing_id": row.id,
            "title": row.title,
            "url": row.url,
        }
        for row in rows
    ]


if __name__ == "__main__":
    asyncio.run(main())
