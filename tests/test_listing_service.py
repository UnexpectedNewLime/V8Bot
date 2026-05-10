"""Tests for listing service user-facing operations."""

import asyncio
from decimal import Decimal

import pytest
from sqlalchemy import select

from car_watch_bot.core.listing_status import (
    LISTING_STATUS_INACTIVE,
    LISTING_STATUS_SENT,
    LISTING_STATUS_STARRED,
)
from car_watch_bot.db.models import WatchListing
from car_watch_bot.db.repositories import (
    SourceRepository,
    UserRepository,
    WatchRepository,
)
from car_watch_bot.scrapers.mock import MockScraper
from car_watch_bot.services.listing_service import (
    ListingService,
    ListingStatusValidationError,
    WatchListingNotFoundError,
)
from car_watch_bot.services.watch_service import WatchNotFoundError, WatchService


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

    result = asyncio.run(
        _listing_service(db_session_factory).scrape_watch_now("123", 1)
    )

    assert result.watch_id == 1
    assert result.sources_seen == 1
    assert result.sources_scraped == 1
    assert result.sources_skipped == 0
    assert result.listings_created == 3
    assert result.pending_listings == 3
    assert result.new_listing_ids == [1, 2, 3]


def test_scrape_watch_now_reports_only_new_pending_listing_ids(
    db_session_factory,
) -> None:
    test_scrape_watch_now_stores_pending_listings(db_session_factory)

    result = asyncio.run(
        _listing_service(db_session_factory).scrape_watch_now("123", 1)
    )
    new_listings = _listing_service(db_session_factory).list_watch_listings(
        "123",
        1,
        listing_ids=result.new_listing_ids,
    )
    all_listings = _listing_service(db_session_factory).list_watch_listings("123", 1)

    assert result.listings_created == 0
    assert result.pending_listings == 3
    assert result.new_listing_ids == []
    assert new_listings == []
    assert len(all_listings) == 3


def test_list_watch_listings_returns_pending_listings(db_session_factory) -> None:
    test_scrape_watch_now_stores_pending_listings(db_session_factory)

    listings = _listing_service(db_session_factory).list_watch_listings("123", 1)

    assert len(listings) == 3
    assert all(listing.url for listing in listings)


def test_watch_listings_includes_sent_listing_history(db_session_factory) -> None:
    test_scrape_watch_now_stores_pending_listings(db_session_factory)
    service = _listing_service(db_session_factory)
    service.mark_watch_listings_sent("123", 1, [1, 2, 3])

    listings = service.list_watch_listings("123", 1)

    assert len(listings) == 3


def test_listing_status_actions_update_visible_history(db_session_factory) -> None:
    test_scrape_watch_now_stores_pending_listings(db_session_factory)
    service = _listing_service(db_session_factory)

    starred = service.update_watch_listing_status(
        "123",
        1,
        1,
        LISTING_STATUS_STARRED,
    )
    inactive = service.update_watch_listing_status(
        "123",
        1,
        2,
        LISTING_STATUS_INACTIVE,
    )

    visible_listing_ids = [
        listing.listing_id for listing in service.list_watch_listings("123", 1)
    ]
    with db_session_factory() as session:
        watch_listings = list(
            session.scalars(select(WatchListing).order_by(WatchListing.listing_id))
        )

    assert starred.status == LISTING_STATUS_STARRED
    assert inactive.status == LISTING_STATUS_INACTIVE
    assert visible_listing_ids == [1, 3]
    assert [row.status for row in watch_listings] == [
        LISTING_STATUS_STARRED,
        LISTING_STATUS_INACTIVE,
        "pending_digest",
    ]
    assert [row.sent_at is not None for row in watch_listings] == [True, True, False]


def test_inactive_listing_is_not_reactivated_by_later_scrapes(
    db_session_factory,
) -> None:
    test_scrape_watch_now_stores_pending_listings(db_session_factory)
    service = _listing_service(db_session_factory)
    service.update_watch_listing_status(
        "123",
        1,
        1,
        LISTING_STATUS_INACTIVE,
    )

    result = asyncio.run(service.scrape_watch_now("123", 1))
    visible_listing_ids = [
        listing.listing_id for listing in service.list_watch_listings("123", 1)
    ]
    with db_session_factory() as session:
        inactive_row = session.scalar(
            select(WatchListing).where(WatchListing.listing_id == 1)
        )

    assert result.new_listing_ids == []
    assert result.pending_listings == 2
    assert visible_listing_ids == [2, 3]
    assert inactive_row is not None
    assert inactive_row.status == LISTING_STATUS_INACTIVE


def test_unstar_watch_listing_restores_sent_history_without_deactivating(
    db_session_factory,
) -> None:
    test_scrape_watch_now_stores_pending_listings(db_session_factory)
    service = _listing_service(db_session_factory)
    service.update_watch_listing_status(
        "123",
        1,
        1,
        LISTING_STATUS_STARRED,
        starred_message_id="555",
    )

    result = service.unstar_watch_listing("123", 1, 1)
    visible_listing_ids = [
        listing.listing_id for listing in service.list_watch_listings("123", 1)
    ]
    with db_session_factory() as session:
        row = session.scalar(select(WatchListing).where(WatchListing.listing_id == 1))

    assert result.status == LISTING_STATUS_SENT
    assert result.starred_message_id == "555"
    assert visible_listing_ids == [1, 2, 3]
    assert row is not None
    assert row.status == LISTING_STATUS_SENT
    assert row.starred_message_id is None


def test_unstar_watch_listing_does_not_reactivate_inactive_listing(
    db_session_factory,
) -> None:
    test_scrape_watch_now_stores_pending_listings(db_session_factory)
    service = _listing_service(db_session_factory)
    service.update_watch_listing_status(
        "123",
        1,
        1,
        LISTING_STATUS_STARRED,
        starred_message_id="555",
    )
    service.update_watch_listing_status("123", 1, 1, LISTING_STATUS_INACTIVE)

    result = service.unstar_watch_listing("123", 1, 1)
    visible_listing_ids = [
        listing.listing_id for listing in service.list_watch_listings("123", 1)
    ]
    with db_session_factory() as session:
        row = session.scalar(select(WatchListing).where(WatchListing.listing_id == 1))

    assert result.status == LISTING_STATUS_INACTIVE
    assert result.starred_message_id is None
    assert visible_listing_ids == [2, 3]
    assert row is not None
    assert row.status == LISTING_STATUS_INACTIVE
    assert row.starred_message_id is None


def test_listing_status_update_is_scoped_to_owner(db_session_factory) -> None:
    test_scrape_watch_now_stores_pending_listings(db_session_factory)

    with pytest.raises(WatchNotFoundError):
        _listing_service(db_session_factory).update_watch_listing_status(
            "456",
            1,
            1,
            LISTING_STATUS_STARRED,
        )


def test_listing_status_update_rejects_unknown_listing(db_session_factory) -> None:
    test_scrape_watch_now_stores_pending_listings(db_session_factory)

    with pytest.raises(WatchListingNotFoundError):
        _listing_service(db_session_factory).update_watch_listing_status(
            "123",
            1,
            999,
            LISTING_STATUS_STARRED,
        )


def test_listing_status_update_rejects_internal_statuses(db_session_factory) -> None:
    test_scrape_watch_now_stores_pending_listings(db_session_factory)

    with pytest.raises(ListingStatusValidationError):
        _listing_service(db_session_factory).update_watch_listing_status(
            "123",
            1,
            1,
            "sent",
        )


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

    result = asyncio.run(
        _listing_service(db_session_factory).scrape_watch_now("123", 1)
    )

    assert result.sources_seen == 1
    assert result.sources_scraped == 0
    assert result.sources_skipped == 1
    assert result.listings_created == 0
    assert result.warnings == ["source 1 skipped: no adapter for custom_website"]
