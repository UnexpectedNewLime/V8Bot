"""Repository tests for the local prototype."""

from decimal import Decimal

from sqlalchemy import text

from car_watch_bot.core.models import ListingCandidate, ScoreResult
from car_watch_bot.db.database import create_database_engine, init_database
from car_watch_bot.db.repositories import (
    PREVIOUS_PRICE_AMOUNT_KEY,
    PREVIOUS_PRICE_CURRENCY_KEY,
    PRICE_CHANGED_AT_KEY,
    ListingRepository,
    SourceRepository,
    UserRepository,
    WatchRepository,
)


def test_init_database_adds_thread_ids_to_existing_watch_table() -> None:
    engine = create_database_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE watches ("
                "id INTEGER PRIMARY KEY, "
                "user_id INTEGER NOT NULL, "
                "name VARCHAR(120) NOT NULL"
                ")"
            )
        )

    init_database(engine)

    with engine.connect() as connection:
        columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(watches)")).fetchall()
        }
    assert "thread_id" in columns
    assert "starred_thread_id" in columns


def test_user_creation_is_idempotent(db_session) -> None:
    users = UserRepository(db_session)

    first_user = users.get_or_create_by_discord_id("123")
    second_user = users.get_or_create_by_discord_id("123")

    assert first_user.id == second_user.id


def test_watch_creation_and_active_listing(db_session) -> None:
    user = UserRepository(db_session).get_or_create_by_discord_id("123")
    watches = WatchRepository(db_session)

    watch = watches.create_watch(
        user_id=user.id,
        name="C5 watch",
        query="C5 Corvette",
        included_keywords=["manual"],
    )

    assert watch in watches.list_active_for_user(user.id)


def test_watch_thread_id_can_be_persisted(db_session) -> None:
    user = UserRepository(db_session).get_or_create_by_discord_id("123")
    watches = WatchRepository(db_session)
    watch = watches.create_watch(
        user_id=user.id,
        name="C5 watch",
        query="C5 Corvette",
        included_keywords=["manual"],
    )

    updated_watch = watches.set_thread_id(watch.id, "555")

    assert updated_watch is not None
    assert updated_watch.thread_id == "555"
    assert watches.list_active_for_user(user.id)[0].thread_id == "555"


def test_watch_starred_thread_id_can_be_persisted(db_session) -> None:
    user = UserRepository(db_session).get_or_create_by_discord_id("123")
    watches = WatchRepository(db_session)
    watch = watches.create_watch(
        user_id=user.id,
        name="C5 watch",
        query="C5 Corvette",
        included_keywords=["manual"],
    )

    updated_watch = watches.set_starred_thread_id(watch.id, "777")

    assert updated_watch is not None
    assert updated_watch.starred_thread_id == "777"
    assert watches.list_active_for_user(user.id)[0].starred_thread_id == "777"


def test_source_creation_and_watch_assignment(db_session) -> None:
    user = UserRepository(db_session).get_or_create_by_discord_id("123")
    watch = WatchRepository(db_session).create_watch(
        user_id=user.id,
        name="C5 watch",
        query="C5 Corvette",
        included_keywords=["manual"],
    )
    sources = SourceRepository(db_session)

    source = sources.create_source(name="Mock Cars")
    sources.add_source_to_watch(watch.id, source.id)

    assert sources.list_sources_for_watch(watch.id) == [source]


def test_listing_dedupe_by_source_url(db_session) -> None:
    source = SourceRepository(db_session).create_source(name="Mock Cars")
    listings = ListingRepository(db_session)
    candidate = ListingCandidate(
        title="C5 Corvette manual",
        url="https://example.test/c5",
        price_amount=Decimal("10000.00"),
        price_currency="USD",
    )
    score = ScoreResult(score=10, is_match=True, reasons=["keyword matched: manual"])

    first_listing, first_created = listings.insert_listing_if_new(
        source_id=source.id,
        listing=candidate,
        score_result=score,
        converted_price_amount=Decimal("15000.00"),
        converted_price_currency="AUD",
        converted_mileage_value=None,
        converted_mileage_unit="km",
    )
    second_listing, second_created = listings.insert_listing_if_new(
        source_id=source.id,
        listing=candidate,
        score_result=score,
        converted_price_amount=Decimal("15000.00"),
        converted_price_currency="AUD",
        converted_mileage_value=None,
        converted_mileage_unit="km",
    )

    assert first_created is True
    assert second_created is False
    assert first_listing.id == second_listing.id


def test_listing_update_records_previous_price_snapshot(db_session) -> None:
    source = SourceRepository(db_session).create_source(name="Mock Cars")
    listings = ListingRepository(db_session)
    score = ScoreResult(score=10, is_match=True, reasons=["keyword matched: manual"])

    listing, created = listings.insert_listing_if_new(
        source_id=source.id,
        listing=ListingCandidate(
            title="C5 Corvette manual",
            url="https://example.test/c5",
            price_amount=Decimal("10000.00"),
            price_currency="USD",
        ),
        score_result=score,
        converted_price_amount=Decimal("15000.00"),
        converted_price_currency="AUD",
        converted_mileage_value=None,
        converted_mileage_unit="km",
    )

    updated_listing, updated_created = listings.insert_listing_if_new(
        source_id=source.id,
        listing=ListingCandidate(
            title="C5 Corvette manual",
            url="https://example.test/c5",
            price_amount=Decimal("9500.00"),
            price_currency="USD",
        ),
        score_result=score,
        converted_price_amount=Decimal("14250.00"),
        converted_price_currency="AUD",
        converted_mileage_value=None,
        converted_mileage_unit="km",
    )

    assert created is True
    assert updated_created is False
    assert updated_listing.id == listing.id
    assert updated_listing.price_amount == Decimal("9500.00")
    assert updated_listing.raw_payload[PREVIOUS_PRICE_AMOUNT_KEY] == "10000.00"
    assert updated_listing.raw_payload[PREVIOUS_PRICE_CURRENCY_KEY] == "USD"
    assert updated_listing.raw_payload[PRICE_CHANGED_AT_KEY].endswith("Z")


def test_unnotified_listing_retrieval_and_mark_notified(db_session) -> None:
    user = UserRepository(db_session).get_or_create_by_discord_id("123")
    watch = WatchRepository(db_session).create_watch(
        user_id=user.id,
        name="C5 watch",
        query="C5 Corvette",
        included_keywords=["manual"],
    )
    source = SourceRepository(db_session).create_source(name="Mock Cars")
    candidate = ListingCandidate(title="C5 Corvette manual", url="https://example.test/c5")
    score = ScoreResult(score=10, is_match=True, reasons=["keyword matched: manual"])
    listings = ListingRepository(db_session)

    listing, _ = listings.insert_listing_if_new(
        source_id=source.id,
        listing=candidate,
        score_result=score,
        converted_price_amount=None,
        converted_price_currency="AUD",
        converted_mileage_value=None,
        converted_mileage_unit="km",
    )
    listings.add_listing_to_watch(watch, listing)

    assert listings.list_unnotified_for_watch(watch.id) == [listing]

    listings.mark_listings_as_notified(watch.id, [listing.id])

    assert listings.list_unnotified_for_watch(watch.id) == []
