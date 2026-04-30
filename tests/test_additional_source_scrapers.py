"""Tests for additional static source scraper adapters."""

import asyncio
from pathlib import Path

import httpx

from car_watch_bot.scrapers.base import ScrapeRequest
from car_watch_bot.scrapers.cars_on_line import CarsOnLineScraper
from car_watch_bot.scrapers.corvette_magazine import CorvetteMagazineScraper
from car_watch_bot.scrapers.diagnostic import DiagnosticScraper
from car_watch_bot.scrapers.vettefinders import VetteFindersScraper


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _scrape_request(source_name: str, source_kind: str, url: str) -> ScrapeRequest:
    """Build a scraper request for tests."""

    return ScrapeRequest(
        source_id=1,
        source_name=source_name,
        source_kind=source_kind,
        base_url=url,
        watch_id=1,
        included_keywords=[],
        excluded_keywords=[],
        criteria_version=1,
    )


def test_cars_on_line_fixture_parses_exact_listing_urls() -> None:
    html = (FIXTURE_DIR / "cars_on_line_search.html").read_text()
    scraper = CarsOnLineScraper(user_agent="V8Bot test")

    listings = scraper.parse_html(
        html,
        "https://cars-on-line.com/search-results/?_sfm__job_listing_year=2000",
    )

    assert len(listings) == 2
    assert listings[0].external_id == "540381"
    assert listings[0].title == "2000 Chevrolet Corvette"
    assert listings[0].url == (
        "https://www.classicautomall.com/vehicles/8018/"
        "2000-chevrolet-corvette-coupe"
    )
    assert listings[0].mileage_value == 60000
    assert listings[0].location_text == "Pennsylvania"
    assert listings[0].price_amount is None
    assert "price missing" in listings[0].raw_payload["warnings"]
    assert listings[1].price_amount is not None
    assert listings[1].price_amount.to_eng_string() == "20000.00"
    assert listings[1].mileage_value == 60000


def test_vettefinders_fixture_parses_summary_rows() -> None:
    html = (FIXTURE_DIR / "vettefinders_summary.html").read_text()
    scraper = VetteFindersScraper(user_agent="V8Bot test")

    listings = scraper.parse_html(
        html,
        "https://www.vettefinders.com/index.cfm/fuseaction/corvette.SummaryView/Gen/5",
    )

    assert len(listings) == 2
    assert listings[0].external_id == "31149"
    assert listings[0].title == "2000 Coupe"
    assert listings[0].url == (
        "https://www.vettefinders.com/index.cfm/"
        "fuseaction=corvette.CarDetail&id=31149&g=5"
    )
    assert listings[0].price_amount is not None
    assert listings[0].price_amount.to_eng_string() == "20000.00"
    assert listings[0].mileage_value == 29351
    assert listings[0].location_text == "WI"


def test_corvette_magazine_fixture_parses_schema_cards() -> None:
    html = (FIXTURE_DIR / "corvette_magazine_classifieds.html").read_text()
    scraper = CorvetteMagazineScraper(user_agent="V8Bot test")

    listings = scraper.parse_html(
        html,
        "https://www.corvette-mag.com/classifieds?from_year=2000",
    )

    assert len(listings) == 2
    assert listings[0].external_id == "20515"
    assert listings[0].title == "2000 Corvette"
    assert listings[0].url == "https://www.corvette-mag.com/classifieds/20515"
    assert listings[0].price_amount is not None
    assert listings[0].price_amount.to_eng_string() == "29000.00"
    assert listings[0].mileage_value == 25612
    assert listings[0].location_text == "Grapevine, TX"
    assert listings[0].raw_payload is not None
    assert listings[0].raw_payload["listed_date"] == "04/27/26"
    assert "Transmission type" in listings[1].description


def test_static_source_fetch_uses_mock_transport() -> None:
    html = (FIXTURE_DIR / "corvette_magazine_classifieds.html").read_text()

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["User-Agent"] == "V8Bot test"
        return httpx.Response(status_code=200, text=html, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    scraper = CorvetteMagazineScraper(user_agent="V8Bot test", http_client=client)

    listings = asyncio.run(
        scraper.fetch_listings(
            _scrape_request(
                "Corvette Magazine",
                "corvette_magazine",
                "https://www.corvette-mag.com/classifieds?from_year=2000",
            )
        )
    )
    asyncio.run(client.aclose())

    assert len(listings) == 2
    assert scraper.build_source_test_result(listings).url_accepted is True


def test_static_source_fetch_error_returns_empty_list() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=403, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    scraper = CarsOnLineScraper(user_agent="V8Bot test", http_client=client)

    listings = asyncio.run(
        scraper.fetch_listings(
            _scrape_request(
                "Cars On Line",
                "cars_on_line",
                "https://cars-on-line.com/search-results/",
            )
        )
    )
    asyncio.run(client.aclose())

    assert listings == []
    assert scraper.last_errors
    assert scraper.build_source_test_result(listings).url_accepted is False


def test_diagnostic_scraper_reports_unsupported_domain_with_polite_fetch() -> None:
    html = """
    <html>
      <head><title>Example Cars</title></head>
      <body>
        <a href="/cars/c5">2001 Corvette manual $20,000 29,000 miles</a>
      </body>
    </html>
    """

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["User-Agent"] == "V8Bot test"
        return httpx.Response(status_code=200, text=html, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    scraper = DiagnosticScraper(user_agent="V8Bot test", http_client=client)

    listings = asyncio.run(
        scraper.fetch_listings(
            _scrape_request(
                "source test",
                "custom_website",
                "https://example.test/search",
            )
        )
    )
    asyncio.run(client.aclose())
    result = scraper.build_source_test_result(listings)

    assert result.url_accepted is False
    assert result.listings_found == 1
    assert result.price_parsing_worked is True
    assert result.mileage_parsing_worked is True
    assert "domain not supported for scheduled scraping: example.test" in result.warnings
    assert "page title: Example Cars" in result.warnings
