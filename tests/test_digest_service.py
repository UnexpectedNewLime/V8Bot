"""Tests for digest formatting from persisted listings."""

import asyncio
from decimal import Decimal

from car_watch_bot.core.models import ListingCandidate, ScoreResult
from car_watch_bot.db.repositories import (
    ListingRepository,
    ScrapeAttemptRepository,
    SourceRepository,
    UserRepository,
    WatchRepository,
)
from car_watch_bot.scrapers.mock import MockScraper
from car_watch_bot.services.digest_service import DigestService
from car_watch_bot.services.scrape_service import ScrapeService


def _seed_digest_data(db_session):
    user = UserRepository(db_session).get_or_create_by_discord_id("123")
    watch = WatchRepository(db_session).create_watch(
        user_id=user.id,
        name="C5 digest",
        query="C5 Corvette",
        included_keywords=["manual", "HUD", "targa"],
        excluded_keywords=["automatic", "convertible"],
    )
    source = SourceRepository(db_session).create_source(name="Mock Cars", kind="mock")
    SourceRepository(db_session).add_source_to_watch(watch.id, source.id)
    service = ScrapeService(
        watch_repository=WatchRepository(db_session),
        source_repository=SourceRepository(db_session),
        listing_repository=ListingRepository(db_session),
        scrape_attempt_repository=ScrapeAttemptRepository(db_session),
        scraper_adapters={"mock": MockScraper()},
        usd_to_aud_rate=Decimal("1.50"),
    )
    asyncio.run(service.run_once())
    return watch


def test_digest_with_multiple_listings(db_session) -> None:
    watch = _seed_digest_data(db_session)
    digest = DigestService(ListingRepository(db_session)).build_digest(watch)

    assert digest is not None
    assert digest.watch_name == "C5 digest"
    assert digest.watch_query == "C5 Corvette"
    assert digest.listing_count == 3
    assert all(listing.url for listing in digest.listings)
    assert any("keyword matched: manual" in listing.score_reasons for listing in digest.listings)


def test_no_empty_digest(db_session) -> None:
    user = UserRepository(db_session).get_or_create_by_discord_id("123")
    watch = WatchRepository(db_session).create_watch(
        user_id=user.id,
        name="Empty digest",
        query="C5 Corvette",
        included_keywords=["manual"],
    )

    digest = DigestService(ListingRepository(db_session)).build_digest(watch)

    assert digest is None


def test_listings_marked_notified_after_successful_digest_call(db_session) -> None:
    watch = _seed_digest_data(db_session)
    listing_repository = ListingRepository(db_session)
    pending = listing_repository.list_unnotified_for_watch(watch.id)

    DigestService(listing_repository).mark_digest_sent(
        watch_id=watch.id,
        listing_ids=[listing.id for listing in pending],
    )

    assert listing_repository.list_unnotified_for_watch(watch.id) == []


def test_digest_uses_listing_source_name_from_raw_payload(db_session) -> None:
    user = UserRepository(db_session).get_or_create_by_discord_id("123")
    watch = WatchRepository(db_session).create_watch(
        user_id=user.id,
        name="C5 digest",
        query="C5 Corvette",
        included_keywords=["manual"],
    )
    source = SourceRepository(db_session).create_source(
        name="User AutoTempest Source",
        kind="autotempest",
    )
    SourceRepository(db_session).add_source_to_watch(watch.id, source.id)
    listing_repository = ListingRepository(db_session)
    listing, _ = listing_repository.insert_listing_if_new(
        source_id=source.id,
        listing=ListingCandidate(
            title="2001 Chevrolet Corvette",
            url="https://www.cars.com/vehicledetail/example/",
            raw_payload={"listing_source_name": "Cars.com"},
        ),
        score_result=ScoreResult(score=10, is_match=True, reasons=["keyword matched"]),
        converted_price_amount=None,
        converted_price_currency=None,
        converted_mileage_value=None,
        converted_mileage_unit=None,
    )
    listing_repository.add_listing_to_watch(watch, listing)

    digest = DigestService(listing_repository).build_digest(watch)

    assert digest is not None
    assert digest.listings[0].source_name == "Cars.com"


def test_digest_formats_prices_without_cents_and_with_commas(db_session) -> None:
    user = UserRepository(db_session).get_or_create_by_discord_id("123")
    watch = WatchRepository(db_session).create_watch(
        user_id=user.id,
        name="C5 digest",
        query="C5 Corvette",
        included_keywords=["manual"],
    )
    source = SourceRepository(db_session).create_source(name="Mock Cars", kind="mock")
    SourceRepository(db_session).add_source_to_watch(watch.id, source.id)
    listing_repository = ListingRepository(db_session)
    listing, _ = listing_repository.insert_listing_if_new(
        source_id=source.id,
        listing=ListingCandidate(
            title="2001 Chevrolet Corvette",
            url="https://example.test/c5",
            price_amount=Decimal("17900.00"),
            price_currency="USD",
        ),
        score_result=ScoreResult(score=10, is_match=True, reasons=["keyword matched"]),
        converted_price_amount=Decimal("26850.00"),
        converted_price_currency="AUD",
        converted_mileage_value=None,
        converted_mileage_unit=None,
    )
    listing_repository.add_listing_to_watch(watch, listing)

    digest = DigestService(listing_repository).build_digest(watch)

    assert digest is not None
    assert digest.listings[0].original_price == "USD 17,900"
    assert digest.listings[0].converted_price == "AUD 26,850"


def test_digest_infers_common_source_name_from_url_for_older_rows(db_session) -> None:
    user = UserRepository(db_session).get_or_create_by_discord_id("123")
    watch = WatchRepository(db_session).create_watch(
        user_id=user.id,
        name="C5 digest",
        query="C5 Corvette",
        included_keywords=["manual"],
    )
    source = SourceRepository(db_session).create_source(
        name="User AutoTempest Source",
        kind="autotempest",
    )
    SourceRepository(db_session).add_source_to_watch(watch.id, source.id)
    listing_repository = ListingRepository(db_session)
    listing, _ = listing_repository.insert_listing_if_new(
        source_id=source.id,
        listing=ListingCandidate(
            title="2001 Chevrolet Corvette",
            url="https://www.ebay.com/itm/147280824884",
            raw_payload={"candidate_type": "queue_result"},
        ),
        score_result=ScoreResult(score=10, is_match=True, reasons=["keyword matched"]),
        converted_price_amount=None,
        converted_price_currency=None,
        converted_mileage_value=None,
        converted_mileage_unit=None,
    )
    listing_repository.add_listing_to_watch(watch, listing)

    digest = DigestService(listing_repository).build_digest(watch)

    assert digest is not None
    assert digest.listings[0].source_name == "eBay"
