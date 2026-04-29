"""Tests for source test behaviour."""

import asyncio
from decimal import Decimal

import pytest
from sqlalchemy import select

from car_watch_bot.core.models import ListingCandidate, SourceTestResult
from car_watch_bot.db.models import SourceTestAttempt
from car_watch_bot.db.repositories import UserRepository
from car_watch_bot.scrapers.base import ScrapeRequest
from car_watch_bot.services.source_service import SourceService, SourceValidationError
from car_watch_bot.services.watch_service import WatchService


class CompleteMockScraper:
    """Mock source test scraper with complete fields."""

    async def fetch_listings(self, request: ScrapeRequest) -> list[ListingCandidate]:
        """Return one complete mock listing."""

        _ = request
        return [
            ListingCandidate(
                title="C5 Corvette manual",
                url="https://example.test/c5",
                price_amount=Decimal("22000.00"),
                price_currency="USD",
                mileage_value=72000,
                mileage_unit="mi",
            )
        ]


class AdapterSpecificScraper:
    """Known-source adapter that provides source-test parse state."""

    @property
    def source_kind(self) -> str:
        """Return source kind."""

        return "autotempest"

    async def fetch_listings(self, request: ScrapeRequest) -> list[ListingCandidate]:
        """Return no exact listings for an AutoTempest static page."""

        _ = request
        return []

    def build_source_test_result(
        self,
        listings: list[ListingCandidate],
    ) -> object:
        """Return adapter-specific source test result."""

        return SourceTestResult(
            url_accepted=True,
            listings_found=len(listings),
            title_parsing_worked=False,
            link_parsing_worked=False,
            price_parsing_worked=False,
            mileage_parsing_worked=False,
            warnings=[
                "static HTML exposed comparison links only; "
                "no exact vehicle listing URLs found"
            ],
            errors=[],
        )


def test_successful_source_test(db_session_factory) -> None:
    with db_session_factory() as session:
        user = UserRepository(session).get_or_create_by_discord_id("123")
        session.commit()
    service = SourceService(
        db_session_factory,
        source_test_scraper=CompleteMockScraper(),
    )

    result = asyncio.run(service.test_source_url(user.discord_user_id, "https://example.test/cars"))

    with db_session_factory() as session:
        attempt = session.scalar(select(SourceTestAttempt))
    assert result.url_accepted is True
    assert result.errors == []
    assert result.warnings == []
    assert attempt.status == "passed"


def test_partial_parse_warning(db_session_factory) -> None:
    with db_session_factory() as session:
        user = UserRepository(session).get_or_create_by_discord_id("123")
        session.commit()
    service = SourceService(db_session_factory)

    result = asyncio.run(service.test_source_url(user.discord_user_id, "https://example.test/cars"))

    assert result.url_accepted is True
    assert "some listings are missing price" in result.warnings
    assert "some listings are missing mileage" in result.warnings


def test_failed_source_test(db_session_factory) -> None:
    with db_session_factory() as session:
        user = UserRepository(session).get_or_create_by_discord_id("123")
        session.commit()
    service = SourceService(db_session_factory)

    result = asyncio.run(service.test_source_url(user.discord_user_id, "not-a-url"))

    with db_session_factory() as session:
        attempt = session.scalar(select(SourceTestAttempt))
    assert result.url_accepted is False
    assert result.errors == ["URL must be http or https"]
    assert attempt.status == "failed"


def test_add_source_to_watch_runs_source_test(db_session_factory) -> None:
    watch_service = WatchService(db_session_factory)
    watch = watch_service.create_watch(
        discord_user_id="123",
        car_query="C5 Corvette",
        keywords="manual",
        exclude_keywords="",
        notify_time="09:30",
    )
    source_service = SourceService(
        db_session_factory,
        source_test_scraper=CompleteMockScraper(),
    )

    result = asyncio.run(
        source_service.add_source_to_watch(
            discord_user_id="123",
            watch_id=watch.watch_id,
            name="Example Cars",
            url="https://example.test/cars",
        )
    )

    assert result.source.source_id == 1
    assert result.source.kind == "custom_website"
    assert result.source_test.url_accepted is True
    assert source_service.list_sources_for_watch("123", watch.watch_id)[0].name == "Example Cars"


def test_add_source_to_watch_reuses_existing_source_with_same_url(db_session_factory) -> None:
    watch_service = WatchService(db_session_factory)
    watch = watch_service.create_watch(
        discord_user_id="123",
        car_query="C5 Corvette",
        keywords="manual",
        exclude_keywords="",
        notify_time="09:30",
    )
    source_service = SourceService(
        db_session_factory,
        source_test_scraper=CompleteMockScraper(),
    )
    first_result = asyncio.run(
        source_service.add_source_to_watch(
            discord_user_id="123",
            watch_id=watch.watch_id,
            name="Example Cars",
            url="https://example.test/cars",
        )
    )

    second_result = asyncio.run(
        source_service.add_source_to_watch(
            discord_user_id="123",
            watch_id=watch.watch_id,
            name="Example Cars",
            url="https://example.test/cars",
        )
    )

    assert second_result.source.source_id == first_result.source.source_id
    assert len(source_service.list_sources_for_watch("123", watch.watch_id)) == 1


def test_add_source_to_watch_rejects_duplicate_name_with_different_url(
    db_session_factory,
) -> None:
    watch_service = WatchService(db_session_factory)
    watch = watch_service.create_watch(
        discord_user_id="123",
        car_query="C5 Corvette",
        keywords="manual",
        exclude_keywords="",
        notify_time="09:30",
    )
    source_service = SourceService(
        db_session_factory,
        source_test_scraper=CompleteMockScraper(),
    )
    asyncio.run(
        source_service.add_source_to_watch(
            discord_user_id="123",
            watch_id=watch.watch_id,
            name="Example Cars",
            url="https://example.test/cars",
        )
    )

    with pytest.raises(SourceValidationError, match="source name already exists"):
        asyncio.run(
            source_service.add_source_to_watch(
                discord_user_id="123",
                watch_id=watch.watch_id,
                name="Example Cars",
                url="https://example.test/other-cars",
            )
        )


def test_add_autotempest_source_uses_autotempest_kind(db_session_factory) -> None:
    watch_service = WatchService(db_session_factory)
    watch = watch_service.create_watch(
        discord_user_id="123",
        car_query="C5 Corvette",
        keywords="manual",
        exclude_keywords="",
        notify_time="09:30",
    )
    source_service = SourceService(
        db_session_factory,
        source_test_scraper=CompleteMockScraper(),
    )

    result = asyncio.run(
        source_service.add_source_to_watch(
            discord_user_id="123",
            watch_id=watch.watch_id,
            name="AutoTempest",
            url="https://www.autotempest.com/results?make=chevrolet",
        )
    )

    assert result.source.kind == "autotempest"


def test_autotempest_source_test_uses_registered_adapter(db_session_factory) -> None:
    with db_session_factory() as session:
        user = UserRepository(session).get_or_create_by_discord_id("123")
        session.commit()
    source_service = SourceService(
        db_session_factory,
        source_test_scrapers={"autotempest": AdapterSpecificScraper()},
    )

    result = asyncio.run(
        source_service.test_source_url(
            user.discord_user_id,
            "https://www.autotempest.com/results?make=chevrolet",
        )
    )

    assert result.listings_found == 0
    assert result.link_parsing_worked is False
    assert (
        "static HTML exposed comparison links only; no exact vehicle listing URLs found"
        in result.warnings
    )


def test_remove_source_from_watch(db_session_factory) -> None:
    watch_service = WatchService(db_session_factory)
    watch = watch_service.create_watch(
        discord_user_id="123",
        car_query="C5 Corvette",
        keywords="manual",
        exclude_keywords="",
        notify_time="09:30",
    )
    source_service = SourceService(
        db_session_factory,
        source_test_scraper=CompleteMockScraper(),
    )
    result = asyncio.run(
        source_service.add_source_to_watch(
            discord_user_id="123",
            watch_id=watch.watch_id,
            name="Example Cars",
            url="https://example.test/cars",
        )
    )

    source_service.remove_source_from_watch(
        discord_user_id="123",
        watch_id=watch.watch_id,
        source_id=result.source.source_id,
    )

    assert source_service.list_sources_for_watch("123", watch.watch_id) == []


def test_add_source_rejects_failed_source_test(db_session_factory) -> None:
    watch_service = WatchService(db_session_factory)
    watch = watch_service.create_watch(
        discord_user_id="123",
        car_query="C5 Corvette",
        keywords="manual",
        exclude_keywords="",
        notify_time="09:30",
    )
    source_service = SourceService(db_session_factory)

    with pytest.raises(SourceValidationError):
        asyncio.run(
            source_service.add_source_to_watch(
                discord_user_id="123",
                watch_id=watch.watch_id,
                name="Bad Source",
                url="not-a-url",
            )
        )

    assert source_service.list_sources_for_watch("123", watch.watch_id) == []
