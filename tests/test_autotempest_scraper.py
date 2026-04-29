"""Tests for AutoTempest static HTML scraping."""

import asyncio
from pathlib import Path

import httpx

from car_watch_bot.scrapers.autotempest import AutoTempestScraper
from car_watch_bot.scrapers.base import ScrapeRequest


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _scrape_request(url: str = "https://www.autotempest.com/results") -> ScrapeRequest:
    """Build a scraper request for tests."""

    return ScrapeRequest(
        source_id=1,
        source_name="AutoTempest",
        source_kind="autotempest",
        base_url=url,
        watch_id=1,
        included_keywords=[],
        excluded_keywords=[],
        criteria_version=1,
    )


def test_parse_listing_cards_from_saved_fixture() -> None:
    html = (FIXTURE_DIR / "autotempest_listing.html").read_text()
    scraper = AutoTempestScraper(user_agent="V8Bot test")

    listings = scraper.parse_html(html, "https://www.autotempest.com/results")

    assert len(listings) == 2
    assert listings[0].title == "2001 Chevrolet Corvette Coupe Manual"
    assert listings[0].url == "https://www.autotempest.com/redirect/listing/at-123"
    assert listings[0].price_amount is not None
    assert listings[0].price_amount.to_eng_string() == "24995.00"
    assert listings[0].mileage_value == 71234
    assert listings[0].location_text == "Beverly Hills, CA"
    assert listings[0].raw_payload is not None
    assert listings[0].raw_payload["candidate_type"] == "vehicle_listing"
    assert listings[0].raw_payload["warnings"] == []
    assert "price missing" in listings[1].raw_payload["warnings"]
    assert "mileage missing" in listings[1].raw_payload["warnings"]


def test_parse_comparison_links_when_static_html_has_no_listings() -> None:
    html = (FIXTURE_DIR / "autotempest_comparison.html").read_text()
    scraper = AutoTempestScraper(
        user_agent="V8Bot test",
        capture_comparison_links=True,
    )

    listings = scraper.parse_html(html, "https://www.autotempest.com/results")

    assert len(listings) == 2
    assert listings[0].title == "AutoTempest comparison link: AutoTrader.com"
    assert listings[0].url == "https://www.autotempest.com/go/autotrader?make=chevrolet"
    assert listings[0].raw_payload is not None
    assert listings[0].raw_payload["candidate_type"] == "comparison_link"
    assert "comparison link only" in listings[0].raw_payload["warnings"][0]
    assert any("Facebook" in warning for warning in scraper.last_warnings)
    source_test = scraper.build_source_test_result(listings)
    assert source_test.url_accepted is True
    assert source_test.listings_found == 2
    assert "skipped Facebook comparison link" in source_test.warnings
    assert (
        "static HTML exposed comparison links only; no exact vehicle listing URLs found"
        in source_test.warnings
    )


def test_comparison_links_are_not_returned_by_default() -> None:
    html = (FIXTURE_DIR / "autotempest_comparison.html").read_text()
    scraper = AutoTempestScraper(user_agent="V8Bot test")

    listings = scraper.parse_html(html, "https://www.autotempest.com/results")
    source_test = scraper.build_source_test_result(listings)

    assert listings == []
    assert (
        "static HTML exposed comparison links only; no exact vehicle listing URLs found"
        in scraper.last_warnings
    )
    assert source_test.title_parsing_worked is False
    assert source_test.link_parsing_worked is False


def test_autotempest_results_urls_are_not_exact_listing_urls() -> None:
    html = """
    <html>
      <body>
        <article class="vehicle-listing" data-listing-id="bad-result-link">
          <a href="/results?make=chevrolet#te-results">Results for Corvette</a>
          <h2>Results for Corvette</h2>
          <span>$1,500</span>
          <span>500 mi</span>
        </article>
      </body>
    </html>
    """
    scraper = AutoTempestScraper(user_agent="V8Bot test")

    listings = scraper.parse_html(
        html,
        "https://www.autotempest.com/results?make=chevrolet",
    )

    assert listings == []


def test_fetch_http_error_returns_empty_list_without_crashing() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=403, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    scraper = AutoTempestScraper(user_agent="V8Bot test", http_client=client)

    listings = asyncio.run(scraper.fetch_listings(_scrape_request()))
    asyncio.run(client.aclose())

    assert listings == []
    assert scraper.last_errors
    source_test = scraper.build_source_test_result(listings)
    assert source_test.url_accepted is False
    assert source_test.errors


def test_fetch_uses_static_html_from_mock_transport() -> None:
    html = (FIXTURE_DIR / "autotempest_listing.html").read_text()

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["User-Agent"] == "V8Bot test"
        return httpx.Response(status_code=200, text=html, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    scraper = AutoTempestScraper(user_agent="V8Bot test", http_client=client)

    listings = asyncio.run(scraper.fetch_listings(_scrape_request()))
    asyncio.run(client.aclose())

    assert len(listings) == 2


def test_fetch_uses_queue_results_for_exact_vehicle_links() -> None:
    html = (FIXTURE_DIR / "autotempest_queue_page.html").read_text()
    queue_json = (FIXTURE_DIR / "autotempest_queue_results.json").read_text()
    requests: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if request.url.path == "/results":
            return httpx.Response(status_code=200, text=html, request=request)
        if request.url.path == "/queue-results":
            assert "token=" in str(request.url)
            if request.url.params.get("sites") == "hem":
                return httpx.Response(
                    status_code=200,
                    json={"status": 1, "results": []},
                    request=request,
                )
            return httpx.Response(status_code=200, text=queue_json, request=request)
        return httpx.Response(status_code=404, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    scraper = AutoTempestScraper(
        user_agent="V8Bot test",
        min_interval_seconds=0,
        http_client=client,
    )

    listings = asyncio.run(scraper.fetch_listings(_scrape_request()))
    asyncio.run(client.aclose())

    assert len(listings) == 1
    assert listings[0].title == "2001 Chevrolet Corvette Z06"
    assert listings[0].url == (
        "https://www.cars.com/vehicledetail/"
        "037c4177-c4e1-4f7a-8eb4-628c64347246/"
    )
    assert listings[0].price_amount is not None
    assert listings[0].price_amount.to_eng_string() == "25995.00"
    assert listings[0].mileage_value == 54222
    assert listings[0].location_text == "Lake Havasu City, AZ"
    assert listings[0].source_name == "Cars.com"
    assert listings[0].raw_payload is not None
    assert listings[0].raw_payload["candidate_type"] == "queue_result"
    assert "skipped Facebook Marketplace source" in scraper.last_warnings
    assert any("/queue-results" in request for request in requests)


def test_search_shell_does_not_create_fake_listing_from_search_url() -> None:
    html = (FIXTURE_DIR / "autotempest_search_shell.html").read_text()
    scraper = AutoTempestScraper(user_agent="V8Bot test")

    listings = scraper.parse_html(
        html,
        "https://www.autotempest.com/results?make=chevrolet",
    )

    assert listings == []
    assert scraper.last_warnings == ["no listing cards or comparison links found"]
