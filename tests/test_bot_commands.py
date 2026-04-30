"""Tests for Discord command formatting helpers."""

import pytest

from car_watch_bot.bot.commands import (
    SourceBatchAddResult,
    _format_sources_added,
    _parse_source_urls,
    _split_discord_message,
    _validate_source_name_usage,
)
from car_watch_bot.core.models import SourceTestResult
from car_watch_bot.services.source_service import (
    SourceAddResult,
    SourceSummary,
    SourceValidationError,
)


def test_split_discord_message_keeps_chunks_under_limit() -> None:
    message = "\n\n".join(
        f"listing_id: {index}\nlink: https://example.test/{index}"
        for index in range(80)
    )

    chunks = _split_discord_message(message)

    assert len(chunks) > 1
    assert all(len(chunk) <= 2000 for chunk in chunks)


def test_split_discord_message_handles_very_long_line() -> None:
    message = "x" * 4500

    chunks = _split_discord_message(message)

    assert [len(chunk) for chunk in chunks] == [1900, 1900, 700]


def test_parse_source_urls_accepts_newlines_commas_and_spaces() -> None:
    raw_urls = """
    https://example.test/one
    https://example.test/two, https://example.test/three
    """

    assert _parse_source_urls(raw_urls) == [
        "https://example.test/one",
        "https://example.test/two",
        "https://example.test/three",
    ]


def test_parse_source_urls_extracts_markdown_links_once() -> None:
    raw_urls = (
        "[https://example.test/one?a=1&b=2]"
        "(https://example.test/one?a=1&b=2), "
        "[https://example.test/two](https://example.test/two), "
        "https://example.test/three"
    )

    assert _parse_source_urls(raw_urls) == [
        "https://example.test/one?a=1&b=2",
        "https://example.test/two",
        "https://example.test/three",
    ]


def test_source_name_is_only_allowed_for_one_url() -> None:
    with pytest.raises(SourceValidationError, match="single URL"):
        _validate_source_name_usage(
            "Example",
            ["https://example.test/one", "https://example.test/two"],
        )


def test_sources_added_summary_is_compact_and_hides_raw_urls() -> None:
    result = SourceBatchAddResult(
        added=[
            SourceAddResult(
                source=SourceSummary(
                    source_id=1,
                    name="cars-on-line",
                    kind="cars_on_line",
                    base_url="https://cars-on-line.com/search-results/?long=query",
                ),
                source_test=SourceTestResult(
                    url_accepted=True,
                    listings_found=11,
                    title_parsing_worked=True,
                    link_parsing_worked=True,
                    price_parsing_worked=False,
                    mileage_parsing_worked=True,
                    warnings=[],
                    errors=[],
                ),
            )
        ],
        failed=[
            (
                "https://www.gatewayclassiccars.com/vehicles/filters/chevrolet/corvette",
                "no scraper adapter is registered for custom_website",
            )
        ],
    )

    message = _format_sources_added(result)

    assert "Added `1` | Not added `1`" in message
    assert "**cars-on-line**" in message
    assert "cars-on-line.com" in message
    assert "search-results" not in message
    assert "gatewayclassiccars.com" in message


def test_sources_added_summary_hides_low_signal_facebook_warning() -> None:
    result = SourceBatchAddResult(
        added=[
            SourceAddResult(
                source=SourceSummary(
                    source_id=5,
                    name="autotempest",
                    kind="autotempest",
                    base_url="https://www.autotempest.com/results?make=chevrolet",
                ),
                source_test=SourceTestResult(
                    url_accepted=True,
                    listings_found=32,
                    title_parsing_worked=True,
                    link_parsing_worked=True,
                    price_parsing_worked=True,
                    mileage_parsing_worked=True,
                    warnings=["skipped Facebook Marketplace source"],
                    errors=[],
                ),
            )
        ],
        failed=[],
    )

    message = _format_sources_added(result)

    assert "autotempest" in message
    assert "Facebook" not in message
    assert "Notes:" not in message
