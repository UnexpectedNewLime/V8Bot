"""Deterministic mock scraper placeholder."""

from decimal import Decimal

from car_watch_bot.core.models import ListingCandidate
from car_watch_bot.scrapers.base import ScrapeRequest


class MockScraper:
    """Mock scraper used by MVP scheduled collection."""

    @property
    def source_kind(self) -> str:
        """Return the mock source kind."""

        return "mock"

    async def fetch_listings(self, request: ScrapeRequest) -> list[ListingCandidate]:
        """Return deterministic mock listings."""

        _ = request
        return [
            ListingCandidate(
                external_id="mock-c5-strong",
                title="2002 Chevrolet Corvette C5 manual HUD targa",
                url="https://example.test/listings/c5-manual-hud-targa",
                description="Clean C5 Corvette coupe with manual gearbox and HUD.",
                price_amount=Decimal("22000.00"),
                price_currency="USD",
                mileage_value=72000,
                mileage_unit="mi",
                location_text="Austin, TX",
                source_name="Mock Cars",
            ),
            ListingCandidate(
                external_id="mock-c5-auto-convertible",
                title="2001 Corvette C5 automatic convertible",
                url="https://example.test/listings/c5-auto-convertible",
                description="Automatic convertible with fresh tyres.",
                price_amount=Decimal("18000.00"),
                price_currency="USD",
                mileage_value=82000,
                mileage_unit="mi",
                location_text="Phoenix, AZ",
                source_name="Mock Cars",
            ),
            ListingCandidate(
                external_id="mock-c5-missing-mileage",
                title="1999 Chevrolet Corvette C5 manual coupe",
                url="https://example.test/listings/c5-manual-missing-mileage",
                description="Manual coupe, mileage not listed.",
                price_amount=Decimal("19500.00"),
                price_currency="USD",
                mileage_value=None,
                mileage_unit=None,
                location_text="Dallas, TX",
                source_name="Mock Cars",
            ),
            ListingCandidate(
                external_id="mock-c5-missing-price",
                title="2003 Chevrolet Corvette C5 Z06 manual",
                url="https://example.test/listings/c5-z06-missing-price",
                description="Z06 manual with targa-like roofline notes.",
                price_amount=None,
                price_currency=None,
                mileage_value=64000,
                mileage_unit="mi",
                location_text="Atlanta, GA",
                source_name="Mock Cars",
            ),
        ]


MockScraperAdapter = MockScraper
