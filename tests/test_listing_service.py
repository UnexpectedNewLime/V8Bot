"""Tests for listing service user-facing operations."""

import asyncio
from decimal import Decimal

from car_watch_bot.db.repositories import SourceRepository, UserRepository, WatchRepository
from car_watch_bot.scrapers.mock import MockScraper
from car_watch_bot.services.listing_service import ListingService
from car_watch_bot.services.watch_service import WatchService


def _listing_service(db_session_factory) -> ListingService:
    """Create listing service with mock scraper."""

    return ListingService(
        db_session_factory,
        scraper_adapters={"mock": MockScraper()},
        usd_to_aud_rate=Decimal("1.50"),
    )


def test_scrape_watch_now_stores_pending_listings(db_session_factory) -> None:
    watch_service = WatchService(db_session_factory)
    watch = watch_service.create_watch(
        discord_user_id="123",
        car_query="C5 Corvette",
        keywords="manual, HUD, targa",
        exclude_keywords="automatic, convertible",
        notify_time="09:30",
    )
    with db_session_factory() as session:
        user = UserRepository(session).get_or_create_by_discord_id("123")
        source = SourceRepository(session).create_source(name="Mock Cars", kind="mock")
        db_watch = WatchRepository(session).get_active_for_user(watch.watch_id, user.id)
        assert db_watch is not None
        SourceRepository(session).add_source_to_watch(db_watch.id, source.id)
        session.commit()

    result = asyncio.run(_listing_service(db_session_factory).scrape_watch_now("123", 1))

    assert result.watch_id == 1
    assert result.sources_seen == 1
    assert result.sources_scraped == 1
    assert result.sources_skipped == 0
    assert result.listings_created == 3
    assert result.pending_listings == 3


def test_list_watch_listings_returns_pending_listings(db_session_factory) -> None:
    test_scrape_watch_now_stores_pending_listings(db_session_factory)

    listings = _listing_service(db_session_factory).list_watch_listings("123", 1)

    assert len(listings) == 3
    assert all(listing.url for listing in listings)


def test_scrape_watch_now_reports_skipped_sources(db_session_factory) -> None:
    watch_service = WatchService(db_session_factory)
    watch = watch_service.create_watch(
        discord_user_id="123",
        car_query="C5 Corvette",
        keywords="manual",
        exclude_keywords="",
        notify_time="09:30",
    )
    with db_session_factory() as session:
        user = UserRepository(session).get_or_create_by_discord_id("123")
        source = SourceRepository(session).create_source(
            name="Unsupported",
            kind="custom_website",
        )
        db_watch = WatchRepository(session).get_active_for_user(watch.watch_id, user.id)
        assert db_watch is not None
        SourceRepository(session).add_source_to_watch(db_watch.id, source.id)
        session.commit()

    result = asyncio.run(_listing_service(db_session_factory).scrape_watch_now("123", 1))

    assert result.sources_seen == 1
    assert result.sources_scraped == 0
    assert result.sources_skipped == 1
    assert result.listings_created == 0
    assert result.warnings == ["source 1 skipped: no adapter for custom_website"]
