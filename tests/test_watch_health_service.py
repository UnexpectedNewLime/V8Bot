"""Tests for watch health diagnostics."""

import pytest

from car_watch_bot.core.models import ListingCandidate, ScoreResult
from car_watch_bot.db.repositories import (
    ListingRepository,
    ScrapeAttemptRepository,
    SourceRepository,
    SourceTestAttemptRepository,
    UserRepository,
    WatchRepository,
)
from car_watch_bot.services.watch_health_service import WatchHealthService
from car_watch_bot.services.watch_service import WatchNotFoundError, WatchService


def test_watch_health_summarizes_scrapes_sources_and_listing_counts(
    db_session_factory,
) -> None:
    watch_service = WatchService(db_session_factory)
    watch = watch_service.create_watch(
        discord_user_id="123",
        car_query="C5 Corvette",
        keywords="manual",
        exclude_keywords="automatic",
        notify_time="09:30",
        guild_id="999",
        channel_id="111",
    )
    with db_session_factory() as session:
        user = UserRepository(session).get_or_create_by_discord_id("123")
        db_watch = WatchRepository(session).get_active_for_user(watch.watch_id, user.id)
        assert db_watch is not None
        WatchRepository(session).set_thread_id(db_watch.id, "222")

        sources = SourceRepository(session)
        mock_source = sources.create_source(
            name="Mock Cars",
            kind="mock",
            owner_user_id=user.id,
            base_url="https://www.example.test/search?zip=90210",
        )
        disabled_source = sources.create_source(
            name="Old Cars",
            kind="mock",
            owner_user_id=user.id,
            base_url="https://old.example.test/search",
        )
        unsupported_source = sources.create_source(
            name="Unsupported",
            kind="custom_website",
            owner_user_id=user.id,
            base_url="https://unsupported.example.test/cars",
        )
        sources.add_source_to_watch(db_watch.id, mock_source.id)
        sources.add_source_to_watch(db_watch.id, disabled_source.id)
        sources.add_source_to_watch(db_watch.id, unsupported_source.id)
        sources.disable_source_for_watch(db_watch.id, disabled_source.id)

        SourceTestAttemptRepository(session).create_attempt(
            user_id=user.id,
            source_id=mock_source.id,
            url=mock_source.base_url or "",
            status="warning",
            notes=["some listings are missing price"],
            detected_links=[],
        )
        SourceTestAttemptRepository(session).create_attempt(
            user_id=user.id,
            source_id=unsupported_source.id,
            url=unsupported_source.base_url or "",
            status="failed",
            notes=[],
            detected_links=[],
            error_message="no scraper adapter is registered for custom_website",
        )

        listings = ListingRepository(session)
        score = ScoreResult(
            score=10,
            is_match=True,
            reasons=["keyword matched: manual"],
        )
        pending_listing, _ = listings.insert_listing_if_new(
            source_id=mock_source.id,
            listing=ListingCandidate(
                title="C5 Corvette manual",
                url="https://example.test/c5-pending",
            ),
            score_result=score,
            converted_price_amount=None,
            converted_price_currency="AUD",
            converted_mileage_value=None,
            converted_mileage_unit="km",
        )
        sent_listing, _ = listings.insert_listing_if_new(
            source_id=mock_source.id,
            listing=ListingCandidate(
                title="C5 Corvette manual sent",
                url="https://example.test/c5-sent",
            ),
            score_result=score,
            converted_price_amount=None,
            converted_price_currency="AUD",
            converted_mileage_value=None,
            converted_mileage_unit="km",
        )
        excluded_listing, _ = listings.insert_listing_if_new(
            source_id=mock_source.id,
            listing=ListingCandidate(
                title="C5 Corvette automatic",
                url="https://example.test/c5-excluded",
            ),
            score_result=score,
            converted_price_amount=None,
            converted_price_currency="AUD",
            converted_mileage_value=None,
            converted_mileage_unit="km",
        )
        listings.add_listing_to_watch(db_watch, pending_listing)
        listings.add_listing_to_watch(db_watch, sent_listing)
        listings.add_listing_to_watch(db_watch, excluded_listing)
        listings.mark_listings_as_notified(db_watch.id, [sent_listing.id])
        listings.exclude_listing_for_watch(db_watch, excluded_listing)

        scrape_attempts = ScrapeAttemptRepository(session)
        scrape_attempts.create_attempt(
            watch_id=db_watch.id,
            source_id=mock_source.id,
            status="success",
            adapter_kind="mock",
            listings_seen=4,
            listings_matched=3,
            listings_created=2,
        )
        scrape_attempts.create_attempt(
            watch_id=db_watch.id,
            source_id=unsupported_source.id,
            status="failed",
            adapter_kind="custom_website",
            error_message=(
                "timeout while fetching https://unsupported.example.test/cars"
            ),
        )
        session.commit()

    health = WatchHealthService(
        db_session_factory,
        registered_source_kinds={"mock"},
    ).get_watch_health("123", watch.watch_id)

    assert health.watch_id == watch.watch_id
    assert health.channel_id == "111"
    assert health.thread_id == "222"
    assert health.source_count == 3
    assert health.active_source_count == 2
    assert health.skipped_source_count == 2
    assert health.disabled_source_count == 1
    assert health.no_adapter_source_count == 1
    assert health.listing_counts.pending_digest == 1
    assert health.listing_counts.sent == 1
    assert health.listing_counts.excluded == 1
    assert health.last_scrape is not None
    assert health.last_scrape.status == "failed"
    assert health.last_failure is not None
    assert health.last_failure.source_name == "Unsupported"
    assert health.last_success is not None
    assert health.last_success.listings_seen == 4
    assert health.recent_scrape_attempts == 2
    assert health.recent_listings_seen == 4
    assert health.recent_listings_matched == 3
    assert health.recent_listings_created == 2
    assert health.sources[0].last_test_status == "warning"
    assert health.sources[0].last_test_notes == ["some listings are missing price"]
    assert health.sources[1].skipped_reason == "disabled for watch"
    assert health.sources[2].skipped_reason == "no adapter for custom_website"


def test_watch_health_handles_empty_history(db_session_factory) -> None:
    watch = WatchService(db_session_factory).create_watch(
        discord_user_id="123",
        car_query="C5 Corvette",
        keywords="manual",
        exclude_keywords="",
        notify_time="09:30",
    )

    health = WatchHealthService(db_session_factory).get_watch_health(
        "123",
        watch.watch_id,
    )

    assert health.source_count == 0
    assert health.listing_counts.total == 0
    assert health.last_scrape is None
    assert health.last_success is None
    assert health.last_failure is None
    assert health.sources == []


def test_watch_health_requires_owned_watch(db_session_factory) -> None:
    watch = WatchService(db_session_factory).create_watch(
        discord_user_id="123",
        car_query="C5 Corvette",
        keywords="manual",
        exclude_keywords="",
        notify_time="09:30",
    )

    with pytest.raises(WatchNotFoundError):
        WatchHealthService(db_session_factory).get_watch_health("456", watch.watch_id)
