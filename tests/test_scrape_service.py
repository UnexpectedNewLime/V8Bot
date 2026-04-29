"""Tests for mock scraper and scrape service pipeline."""

import asyncio
from decimal import Decimal

from sqlalchemy import func, select

from car_watch_bot.db.models import Listing, ScrapeAttempt
from car_watch_bot.db.repositories import (
    ListingRepository,
    ScrapeAttemptRepository,
    SourceRepository,
    UserRepository,
    WatchRepository,
)
from car_watch_bot.scrapers.base import ScrapeRequest
from car_watch_bot.scrapers.mock import MockScraper
from car_watch_bot.services.scrape_service import ScrapeService


def _create_c5_watch_with_mock_source(db_session) -> tuple[int, int]:
    user = UserRepository(db_session).get_or_create_by_discord_id("123")
    watch = WatchRepository(db_session).create_watch(
        user_id=user.id,
        name="C5 manual watch",
        query="C5 Corvette",
        included_keywords=["manual", "HUD", "targa"],
        excluded_keywords=["automatic", "convertible"],
    )
    source = SourceRepository(db_session).create_source(name="Mock Cars", kind="mock")
    SourceRepository(db_session).add_source_to_watch(watch.id, source.id)
    return watch.id, source.id


def _create_scrape_service(db_session) -> ScrapeService:
    return ScrapeService(
        watch_repository=WatchRepository(db_session),
        source_repository=SourceRepository(db_session),
        listing_repository=ListingRepository(db_session),
        scrape_attempt_repository=ScrapeAttemptRepository(db_session),
        scraper_adapters={"mock": MockScraper()},
        usd_to_aud_rate=Decimal("1.50"),
    )


def test_mock_scraper_returns_required_listing_shapes() -> None:
    scraper = MockScraper()
    listings = asyncio.run(
        scraper.fetch_listings(
            ScrapeRequest(
                source_id=1,
                source_name="Mock Cars",
                source_kind="mock",
                base_url=None,
                watch_id=1,
                included_keywords=[],
                excluded_keywords=[],
                criteria_version=1,
            )
        )
    )

    assert len(listings) == 4
    assert any("manual HUD targa" in listing.title for listing in listings)
    assert any("automatic convertible" in listing.title for listing in listings)
    assert any(listing.mileage_value is None for listing in listings)
    assert any(listing.price_amount is None for listing in listings)


def test_scrape_service_stores_matching_listings_only(db_session) -> None:
    watch_id, _ = _create_c5_watch_with_mock_source(db_session)
    service = _create_scrape_service(db_session)

    created_count = asyncio.run(service.run_once())

    pending_listings = ListingRepository(db_session).list_unnotified_for_watch(watch_id)
    titles = [listing.title for listing in pending_listings]
    assert created_count == 3
    assert len(pending_listings) == 3
    assert not any("automatic convertible" in title for title in titles)


def test_repeated_scrape_does_not_duplicate_listings(db_session) -> None:
    _create_c5_watch_with_mock_source(db_session)
    service = _create_scrape_service(db_session)

    first_created = asyncio.run(service.run_once())
    second_created = asyncio.run(service.run_once())

    listing_count = db_session.scalar(select(func.count()).select_from(Listing))
    attempt_count = db_session.scalar(select(func.count()).select_from(ScrapeAttempt))
    assert first_created == 3
    assert second_created == 0
    assert listing_count == 3
    assert attempt_count == 2


def test_excluded_keyword_listing_is_not_persisted(db_session) -> None:
    _create_c5_watch_with_mock_source(db_session)

    asyncio.run(_create_scrape_service(db_session).run_once())

    titles = list(db_session.scalars(select(Listing.title)))
    assert "2001 Corvette C5 automatic convertible" not in titles
