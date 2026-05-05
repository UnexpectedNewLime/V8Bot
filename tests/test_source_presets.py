"""Tests for guided source preset helpers."""

import asyncio
from decimal import Decimal

import pytest

from car_watch_bot.core.models import ListingCandidate
from car_watch_bot.core.source_presets import (
    AutoTempestSearchCriteria,
    SourcePresetValidationError,
    build_autotempest_keywords,
    build_autotempest_source_name,
    build_autotempest_url,
    build_autotempest_watch_query,
)
from car_watch_bot.scrapers.base import ScrapeRequest
from car_watch_bot.services.listing_service import ListingService
from car_watch_bot.services.source_preset_service import SourcePresetService
from car_watch_bot.services.source_service import SourceService
from car_watch_bot.services.watch_service import WatchService


class AutoTempestMockScraper:
    """AutoTempest adapter double for source tests and scrape-now."""

    @property
    def source_kind(self) -> str:
        """Return source kind."""

        return "autotempest"

    async def fetch_listings(self, request: ScrapeRequest) -> list[ListingCandidate]:
        """Return one matching listing."""

        assert request.source_kind == "autotempest"
        return [
            ListingCandidate(
                title="2001 Chevrolet Corvette manual coupe",
                url="https://example.test/corvette-2001",
                price_amount=Decimal("25000.00"),
                price_currency="USD",
                mileage_value=55000,
                mileage_unit="mi",
            )
        ]


def test_build_autotempest_url_is_deterministic() -> None:
    criteria = AutoTempestSearchCriteria(
        make=" Chevrolet ",
        model=" Corvette ",
        year_min=1997,
        year_max=2004,
        transmission="manual",
        zip_postcode="90210",
        radius=500,
    )

    url = build_autotempest_url(criteria)

    assert url == (
        "https://www.autotempest.com/results?"
        "localization=any&make=chevrolet&model=corvette&minyear=1997"
        "&maxyear=2004&transmission=man&zip=90210&radius=500"
    )


def test_build_autotempest_url_omits_empty_filters_and_encodes_text() -> None:
    criteria = AutoTempestSearchCriteria(
        make="Alfa Romeo",
        model="Giulia Quadrifoglio",
        transmission="any",
    )

    url = build_autotempest_url(criteria)

    assert url == (
        "https://www.autotempest.com/results?"
        "localization=any&make=alfa+romeo&model=giulia+quadrifoglio"
    )


def test_build_autotempest_url_validates_range_and_radius() -> None:
    with pytest.raises(SourcePresetValidationError, match="year_min"):
        build_autotempest_url(
            AutoTempestSearchCriteria(
                make="Chevrolet",
                model="Corvette",
                year_min=2004,
                year_max=1997,
            )
        )

    with pytest.raises(SourcePresetValidationError, match="zip_postcode"):
        build_autotempest_url(
            AutoTempestSearchCriteria(
                make="Chevrolet",
                model="Corvette",
                radius=500,
            )
        )


def test_autotempest_watch_text_helpers() -> None:
    criteria = AutoTempestSearchCriteria(
        make="Chevrolet",
        model="Corvette",
        year_min=2001,
        year_max=2001,
        transmission="manual",
    )

    assert build_autotempest_watch_query(criteria) == "2001 Chevrolet Corvette"
    assert (
        build_autotempest_source_name(criteria)
        == "AutoTempest Chevrolet Corvette 2001"
    )
    assert build_autotempest_keywords(criteria, "") == "Corvette, manual"
    assert build_autotempest_keywords(criteria, "manual, targa") == "manual, targa"


def test_source_preset_service_attaches_generated_autotempest_source(
    db_session_factory,
) -> None:
    watch_service = WatchService(db_session_factory)
    source_service = SourceService(
        db_session_factory,
        source_test_scrapers={"autotempest": AutoTempestMockScraper()},
        allow_unregistered_sources=False,
    )
    listing_service = ListingService(
        db_session_factory,
        scraper_adapters={"autotempest": AutoTempestMockScraper()},
        usd_to_aud_rate=Decimal("1.50"),
    )
    preset_service = SourcePresetService(
        watch_service=watch_service,
        source_service=source_service,
        listing_service=listing_service,
    )

    result = asyncio.run(
        preset_service.add_autotempest_watch(
            discord_user_id="123",
            make="Chevrolet",
            model="Corvette",
            notify_time="09:30",
            year_min=2001,
            year_max=2001,
            transmission="manual",
            zip_postcode="90210",
            radius=500,
            keywords="",
            exclude_keywords="automatic",
            guild_id="456",
            channel_id="789",
            scrape_now=False,
        )
    )

    sources = source_service.list_sources_for_watch("123", result.watch.watch_id)
    assert result.watch.car_query == "2001 Chevrolet Corvette"
    assert result.watch.keywords == ["Corvette", "manual"]
    assert result.source_url == (
        "https://www.autotempest.com/results?"
        "localization=any&make=chevrolet&model=corvette&minyear=2001"
        "&maxyear=2001&transmission=man&zip=90210&radius=500"
    )
    assert result.source_result.source.kind == "autotempest"
    assert sources[0].base_url == result.source_url
    assert result.scrape_result is None
    assert result.listings == []


def test_source_preset_service_can_scrape_now(db_session_factory) -> None:
    watch_service = WatchService(db_session_factory)
    scraper = AutoTempestMockScraper()
    source_service = SourceService(
        db_session_factory,
        source_test_scrapers={"autotempest": scraper},
        allow_unregistered_sources=False,
    )
    listing_service = ListingService(
        db_session_factory,
        scraper_adapters={"autotempest": scraper},
        usd_to_aud_rate=Decimal("1.50"),
    )
    preset_service = SourcePresetService(
        watch_service=watch_service,
        source_service=source_service,
        listing_service=listing_service,
    )

    result = asyncio.run(
        preset_service.add_autotempest_watch(
            discord_user_id="123",
            make="Chevrolet",
            model="Corvette",
            notify_time="09:30",
            year_min=2001,
            year_max=2001,
            transmission="manual",
            zip_postcode="90210",
            radius=500,
            keywords="manual",
            exclude_keywords="automatic",
            guild_id="456",
            channel_id="789",
            scrape_now=True,
        )
    )

    assert result.scrape_result is not None
    assert result.scrape_result.sources_scraped == 1
    assert result.scrape_result.new_listing_ids == [1]
    assert [listing.title for listing in result.listings] == [
        "2001 Chevrolet Corvette manual coupe"
    ]
