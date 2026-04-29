"""Run one polite manual AutoTempest scrape for local development."""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from car_watch_bot.config import get_settings  # noqa: E402
from car_watch_bot.scrapers.autotempest import AutoTempestScraper  # noqa: E402
from car_watch_bot.scrapers.base import ScrapeRequest  # noqa: E402


DEFAULT_URL = (
    "https://www.autotempest.com/results?"
    "localization=any&make=chevrolet&maxyear=2001&minyear=2001&"
    "model=corvette&transmission=man&zip=90210"
)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description="Run AutoTempest scraping without Discord or persistence.",
    )
    parser.add_argument("url", nargs="?", help="Full AutoTempest search URL.")
    parser.add_argument("--make", dest="make_name")
    parser.add_argument("--model")
    parser.add_argument("--minyear", type=int)
    parser.add_argument("--maxyear", type=int)
    parser.add_argument("--year", type=int, help="Set minyear and maxyear together.")
    parser.add_argument("--transmission", choices=["any", "auto", "man"])
    parser.add_argument("--zip", dest="zip_code")
    parser.add_argument("--localization", default="any")
    parser.add_argument("--include-comparison-links", action="store_true")
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print compact listing rows instead of full JSON.",
    )
    return parser.parse_args()


async def main() -> None:
    """Run one manual scrape and write JSON to stdout."""

    settings = get_settings()
    args = parse_args()
    url = args.url or _url_from_args(args)
    scraper = AutoTempestScraper(
        user_agent=settings.scraper_user_agent,
        timeout_seconds=settings.scraper_timeout_seconds,
        min_interval_seconds=settings.scraper_min_interval_seconds,
        capture_comparison_links=args.include_comparison_links,
    )
    listings = await scraper.fetch_listings(
        ScrapeRequest(
            source_id=0,
            source_name="AutoTempest",
            source_kind="autotempest",
            base_url=url,
            watch_id=0,
            included_keywords=[],
            excluded_keywords=[],
            criteria_version=1,
        )
    )
    source_test = scraper.build_source_test_result(listings)
    payload: dict[str, Any] = {
        "listing_count": len(listings),
        "warnings": scraper.last_warnings,
        "errors": scraper.last_errors,
        "source_test": {
            "url_accepted": source_test.url_accepted,
            "listings_found": source_test.listings_found,
            "title_parsing_worked": source_test.title_parsing_worked,
            "link_parsing_worked": source_test.link_parsing_worked,
            "price_parsing_worked": source_test.price_parsing_worked,
            "mileage_parsing_worked": source_test.mileage_parsing_worked,
            "warnings": source_test.warnings,
            "errors": source_test.errors,
        },
        "listings": [
            {
                "title": listing.title,
                "url": listing.url,
                "price_amount": str(listing.price_amount)
                if listing.price_amount is not None
                else None,
                "price_currency": listing.price_currency,
                "mileage_value": listing.mileage_value,
                "mileage_unit": listing.mileage_unit,
                "location_text": listing.location_text,
                "source_name": listing.source_name,
                "raw_payload": listing.raw_payload,
            }
            for listing in listings
        ],
    }
    if args.summary:
        sys.stdout.write(_format_summary(payload))
    else:
        sys.stdout.write(json.dumps(payload, indent=2))
    sys.stdout.write("\n")


def _url_from_args(args: argparse.Namespace) -> str:
    """Build an AutoTempest search URL from CLI arguments."""

    if not any(
        [
            args.make_name,
            args.model,
            args.minyear,
            args.maxyear,
            args.year,
            args.transmission,
            args.zip_code,
        ]
    ):
        return DEFAULT_URL

    minyear = args.year if args.year is not None else args.minyear
    maxyear = args.year if args.year is not None else args.maxyear
    query_params = {
        "localization": args.localization,
        "make": args.make_name,
        "model": args.model,
        "minyear": minyear,
        "maxyear": maxyear,
        "transmission": args.transmission,
        "zip": args.zip_code,
    }
    encoded_params = urlencode(
        {
            key: value
            for key, value in query_params.items()
            if value is not None and value != ""
        }
    )
    return f"https://www.autotempest.com/results?{encoded_params}"


def _format_summary(payload: dict[str, Any]) -> str:
    """Format compact scraper output for terminal inspection."""

    lines = [
        f"listing_count: {payload['listing_count']}",
        f"warnings: {', '.join(payload['warnings']) or 'none'}",
        f"errors: {', '.join(payload['errors']) or 'none'}",
        "",
    ]
    for index, listing in enumerate(payload["listings"], 1):
        lines.extend(
            [
                f"{index}. {listing['title']}",
                f"   source: {listing['source_name']}",
                f"   price: {_format_value(listing['price_amount'], listing['price_currency'])}",
                f"   mileage: {_format_value(listing['mileage_value'], listing['mileage_unit'])}",
                f"   location: {listing['location_text']}",
                f"   url: {listing['url']}",
                "",
            ]
        )
    return "\n".join(lines).rstrip()


def _format_value(value: object, unit: object) -> str:
    """Format optional value/unit pairs for terminal output."""

    if value is None or unit is None:
        return "not listed"
    return f"{unit} {value}"


if __name__ == "__main__":
    asyncio.run(main())
