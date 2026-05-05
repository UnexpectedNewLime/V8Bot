"""Tests for Discord command formatting helpers."""

import asyncio
from pathlib import Path

import pytest

from car_watch_bot.bot.commands import (
    ScrapeNowMode,
    SourceBatchAddResult,
    _coerce_scrape_now_mode,
    _format_scrape_now_mode_result,
    _format_sources_added,
    _parse_source_urls,
    _run_watch_scrape_now,
    _split_discord_message,
    _validate_source_name_usage,
)
from car_watch_bot.core.models import DigestListing, ScrapeNowResult, SourceTestResult
from car_watch_bot.services.source_service import (
    SourceAddResult,
    SourceSummary,
    SourceValidationError,
)
from car_watch_bot.services.watch_service import WatchValidationError


ROOT = Path(__file__).resolve().parents[1]


class _FakeUser:
    """Minimal interaction user fake."""

    id = 123


class _FakeInteraction:
    """Minimal interaction fake for command runner tests."""

    user = _FakeUser()


class _FakeListingService:
    """Listing service fake that records scrape-now side effects."""

    def __init__(self) -> None:
        self.result = ScrapeNowResult(
            watch_id=7,
            sources_seen=1,
            sources_scraped=1,
            sources_skipped=0,
            listings_created=2,
            pending_listings=2,
            warnings=[],
            new_listing_ids=[10, 11],
        )
        self.listings = [
            DigestListing(
                listing_id=10,
                title="2001 Chevrolet Corvette",
                source_name="Mock Cars",
                original_price="USD 20,000",
                converted_price="AUD 30,000",
                original_mileage="50,000 mi",
                converted_mileage="80,467 km",
                score_reasons=["keyword matched: manual"],
                url="https://example.test/10",
            ),
            DigestListing(
                listing_id=11,
                title="2002 Chevrolet Corvette Z06",
                source_name="Mock Cars",
                original_price="USD 28,000",
                converted_price="AUD 42,000",
                original_mileage="42,000 mi",
                converted_mileage="67,592 km",
                score_reasons=["keyword matched: Z06"],
                url="https://example.test/11",
            ),
        ]
        self.scrape_calls: list[tuple[str, int]] = []
        self.list_calls: list[tuple[str, int, list[int] | None]] = []
        self.mark_calls: list[tuple[str, int, list[int]]] = []

    async def scrape_watch_now(
        self,
        discord_user_id: str,
        watch_id: int,
    ) -> ScrapeNowResult:
        self.scrape_calls.append((discord_user_id, watch_id))
        return self.result

    def list_watch_listings(
        self,
        discord_user_id: str,
        watch_id: int,
        listing_ids: list[int] | None = None,
    ) -> list[DigestListing]:
        self.list_calls.append((discord_user_id, watch_id, listing_ids))
        return self.listings

    def mark_watch_listings_sent(
        self,
        discord_user_id: str,
        watch_id: int,
        listing_ids: list[int],
    ) -> None:
        self.mark_calls.append((discord_user_id, watch_id, listing_ids))


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


def test_scrape_now_mode_coercion_accepts_known_modes() -> None:
    mode = _coerce_scrape_now_mode("post_but_keep_pending")

    assert mode == ScrapeNowMode.POST_BUT_KEEP_PENDING


def test_scrape_now_mode_coercion_rejects_unknown_modes() -> None:
    with pytest.raises(WatchValidationError, match="mode must be one of"):
        _coerce_scrape_now_mode("surprise_me")


def test_scrape_now_preview_response_includes_compact_listing_preview() -> None:
    result = ScrapeNowResult(
        watch_id=7,
        sources_seen=1,
        sources_scraped=1,
        sources_skipped=0,
        listings_created=1,
        pending_listings=1,
        warnings=[],
        new_listing_ids=[10],
    )
    listing = DigestListing(
        listing_id=10,
        title="2001 Chevrolet Corvette",
        source_name="Mock Cars",
        original_price="USD 20,000",
        converted_price="AUD 30,000",
        original_mileage="50,000 mi",
        converted_mileage="80,467 km",
        score_reasons=["keyword matched: manual"],
        url="https://example.test/10",
    )

    message = _format_scrape_now_mode_result(
        result=result,
        listings=[listing],
        mode=ScrapeNowMode.PREVIEW_ONLY,
        posted_count=0,
    )

    assert "Mode: `preview_only`" in message
    assert "Pending digest state: kept; nothing was posted publicly." in message
    assert "**Preview**" in message
    assert "2001 Chevrolet Corvette" in message


def test_watch_scrape_now_default_posts_and_marks_seen(monkeypatch: pytest.MonkeyPatch) -> None:
    listing_service = _FakeListingService()
    sent_batches: list[dict[str, object]] = []

    async def fake_send_public_listing_embeds(*args: object, **kwargs: object) -> None:
        sent_batches.append(kwargs)

    monkeypatch.setattr(
        "car_watch_bot.bot.commands._send_public_listing_embeds",
        fake_send_public_listing_embeds,
    )

    message = asyncio.run(
        _run_watch_scrape_now(
            interaction=_FakeInteraction(),
            watch_service=object(),
            listing_service=listing_service,
            watch_id=7,
            mode=ScrapeNowMode.POST_AND_MARK_SEEN,
        )
    )

    assert listing_service.scrape_calls == [("123", 7)]
    assert listing_service.list_calls == [("123", 7, [10, 11])]
    assert len(sent_batches) == 1
    assert listing_service.mark_calls == [("123", 7, [10, 11])]
    assert "Posted new listing messages: `2`" in message
    assert "Pending digest state: consumed" in message


def test_watch_scrape_now_preview_keeps_pending_without_public_post(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listing_service = _FakeListingService()
    sent_batches: list[dict[str, object]] = []

    async def fake_send_public_listing_embeds(*args: object, **kwargs: object) -> None:
        sent_batches.append(kwargs)

    monkeypatch.setattr(
        "car_watch_bot.bot.commands._send_public_listing_embeds",
        fake_send_public_listing_embeds,
    )

    message = asyncio.run(
        _run_watch_scrape_now(
            interaction=_FakeInteraction(),
            watch_service=object(),
            listing_service=listing_service,
            watch_id=7,
            mode=ScrapeNowMode.PREVIEW_ONLY,
        )
    )

    assert listing_service.scrape_calls == [("123", 7)]
    assert listing_service.list_calls == [("123", 7, [10, 11])]
    assert sent_batches == []
    assert listing_service.mark_calls == []
    assert "Previewed new listings: `2`" in message
    assert "Pending digest state: kept; nothing was posted publicly." in message


def test_watch_scrape_now_post_but_keep_pending_does_not_mark_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listing_service = _FakeListingService()
    sent_batches: list[dict[str, object]] = []

    async def fake_send_public_listing_embeds(*args: object, **kwargs: object) -> None:
        sent_batches.append(kwargs)

    monkeypatch.setattr(
        "car_watch_bot.bot.commands._send_public_listing_embeds",
        fake_send_public_listing_embeds,
    )

    message = asyncio.run(
        _run_watch_scrape_now(
            interaction=_FakeInteraction(),
            watch_service=object(),
            listing_service=listing_service,
            watch_id=7,
            mode=ScrapeNowMode.POST_BUT_KEEP_PENDING,
        )
    )

    assert listing_service.scrape_calls == [("123", 7)]
    assert listing_service.list_calls == [("123", 7, [10, 11])]
    assert len(sent_batches) == 1
    assert listing_service.mark_calls == []
    assert "Posted new listing messages: `2`" in message
    assert "Pending digest state: kept; scheduled digests can still send" in message


def test_scrape_now_modes_are_documented() -> None:
    documented_files = [
        "README.md",
        "docs/04-command-design.md",
        "docs/manual-testing-preview-notify-semantics.md",
        "docs/ralph-loop-preview-notify-semantics.md",
    ]

    for relative_path in documented_files:
        text = (ROOT / relative_path).read_text(encoding="utf-8")
        for mode in ScrapeNowMode:
            assert mode.value in text
