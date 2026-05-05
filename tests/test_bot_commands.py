"""Tests for Discord command formatting helpers."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from car_watch_bot.bot.commands import (
    ScrapeNowMode,
    SourceBatchAddResult,
    _coerce_scrape_now_mode,
    _format_scrape_now_mode_result,
    _format_sources_added,
    _format_watch_details,
    _format_watch_edit_result,
    _parse_source_urls,
    _run_watch_scrape_now,
    _source_id_autocomplete_choices,
    _source_remove_options,
    _split_discord_message,
    _truncate_discord_label,
    _validate_source_name_usage,
    _watch_id_autocomplete_choices,
)
from car_watch_bot.core.models import DigestListing, ScrapeNowResult, SourceTestResult
from car_watch_bot.services.source_service import (
    SourceAddResult,
    SourceSummary,
    SourceValidationError,
)
from car_watch_bot.services.watch_service import (
    WatchDetails,
    WatchService,
    WatchSourceDetails,
    WatchUpdateResult,
    WatchValidationError,
)


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


def _interaction(user_id: str = "123", watch_id: int | None = None) -> SimpleNamespace:
    namespace = SimpleNamespace()
    if watch_id is not None:
        namespace.watch_id = watch_id
    return SimpleNamespace(user=SimpleNamespace(id=user_id), namespace=namespace)


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


def test_watch_id_autocomplete_choices_are_user_scoped(
    db_session_factory,
) -> None:
    watch_service = WatchService(db_session_factory)
    c5_watch = watch_service.create_watch(
        discord_user_id="123",
        car_query="C5 Corvette",
        keywords="manual, targa",
        exclude_keywords="automatic",
        notify_time="09:30",
    )
    watch_service.create_watch(
        discord_user_id="456",
        car_query="C5 Corvette Z06",
        keywords="manual",
        exclude_keywords="",
        notify_time="09:30",
    )
    watch_service.create_watch(
        discord_user_id="123",
        car_query="HQ Monaro",
        keywords="coupe",
        exclude_keywords="",
        notify_time="09:30",
    )

    choices = asyncio.run(
        _watch_id_autocomplete_choices(
            _interaction("123"),
            "c5",
            watch_service,
        )
    )

    assert [choice.value for choice in choices] == [c5_watch.watch_id]
    assert choices[0].name.startswith(f"#{c5_watch.watch_id} C5 Corvette")


def test_watch_id_autocomplete_accepts_numeric_current(db_session_factory) -> None:
    watch_service = WatchService(db_session_factory)
    watch = watch_service.create_watch(
        discord_user_id="123",
        car_query="C5 Corvette",
        keywords="manual",
        exclude_keywords="",
        notify_time="09:30",
    )

    choices = asyncio.run(
        _watch_id_autocomplete_choices(
            _interaction("123"),
            watch.watch_id,
            watch_service,
        )
    )

    assert [choice.value for choice in choices] == [watch.watch_id]


def test_watch_id_autocomplete_limits_choices(db_session_factory) -> None:
    watch_service = WatchService(db_session_factory)
    for index in range(30):
        watch_service.create_watch(
            discord_user_id="123",
            car_query=f"Watch {index}",
            keywords="manual",
            exclude_keywords="",
            notify_time="09:30",
        )

    choices = asyncio.run(
        _watch_id_autocomplete_choices(
            _interaction("123"),
            "",
            watch_service,
        )
    )

    assert len(choices) == 25
    assert choices[0].value == 1
    assert choices[-1].value == 25


def test_source_id_autocomplete_uses_selected_watch() -> None:
    class FakeSourceService:
        def __init__(self) -> None:
            self.calls: list[tuple[str, int]] = []

        def list_sources_for_watch(
            self,
            discord_user_id: str,
            watch_id: int,
        ) -> list[SourceSummary]:
            self.calls.append((discord_user_id, watch_id))
            return [
                SourceSummary(
                    source_id=7,
                    name="AutoTempest",
                    kind="autotempest",
                    base_url="https://www.autotempest.com/results?make=chevrolet",
                ),
                SourceSummary(
                    source_id=8,
                    name="Example Cars",
                    kind="custom_website",
                    base_url="https://example.test/cars",
                ),
            ]

    source_service = FakeSourceService()

    choices = asyncio.run(
        _source_id_autocomplete_choices(
            _interaction("123", watch_id=42),
            "example",
            source_service,
        )
    )

    assert source_service.calls == [("123", 42)]
    assert [choice.value for choice in choices] == [8]
    assert choices[0].name == "#8 Example Cars (custom_website, example.test)"


def test_source_id_autocomplete_accepts_numeric_current() -> None:
    class FakeSourceService:
        def list_sources_for_watch(
            self,
            discord_user_id: str,
            watch_id: int,
        ) -> list[SourceSummary]:
            return [
                SourceSummary(
                    source_id=7,
                    name="AutoTempest",
                    kind="autotempest",
                    base_url="https://www.autotempest.com/results?make=chevrolet",
                ),
                SourceSummary(
                    source_id=8,
                    name="Example Cars",
                    kind="custom_website",
                    base_url="https://example.test/cars",
                ),
            ]

    choices = asyncio.run(
        _source_id_autocomplete_choices(
            _interaction("123", watch_id=42),
            7,
            FakeSourceService(),
        )
    )

    assert [choice.value for choice in choices] == [7]


def test_source_id_autocomplete_waits_for_watch_selection() -> None:
    class FakeSourceService:
        def list_sources_for_watch(
            self,
            discord_user_id: str,
            watch_id: int,
        ) -> list[SourceSummary]:
            raise AssertionError("source lookup should not run")

    choices = asyncio.run(
        _source_id_autocomplete_choices(
            _interaction("123"),
            "",
            FakeSourceService(),
        )
    )

    assert choices == []


def test_source_remove_options_are_discord_safe() -> None:
    options = _source_remove_options(
        [
            SourceSummary(
                source_id=7,
                name="A" * 120,
                kind="custom_website",
                base_url="https://example.test/a/very/long/path",
            )
        ]
    )

    assert options[0].value == "7"
    assert len(options[0].label) == 100
    assert options[0].label.endswith("...")
    assert options[0].description == "custom_website - example.test"


def test_truncate_discord_label_compacts_whitespace() -> None:
    label = _truncate_discord_label("one\n\n two   three", limit=12)

    assert label == "one two t..."


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
    ]

    for relative_path in documented_files:
        text = (ROOT / relative_path).read_text(encoding="utf-8")
        for mode in ScrapeNowMode:
            assert mode.value in text


def test_watch_details_summary_includes_full_surface_and_sources() -> None:
    details = WatchDetails(
        watch_id=7,
        name="C5 Z06 hunt",
        car_query="C5 Corvette Z06",
        keywords=["manual", "z06"],
        exclude_keywords=["automatic"],
        notify_time="21:45",
        timezone="Australia/Sydney",
        preferred_currency="AUD",
        distance_unit="km",
        guild_id="111",
        channel_id="222",
        thread_id=None,
        criteria_version=3,
        is_active=True,
        active_sources_count=1,
        sources=[
            WatchSourceDetails(
                source_id=9,
                name="AutoTempest",
                kind="autotempest",
                base_url="https://www.autotempest.com/results?make=chevrolet",
                is_enabled=True,
                is_active=True,
            )
        ],
    )

    message = _format_watch_details(details)

    assert "**Watch details**" in message
    assert "`#7` **C5 Z06 hunt**" in message
    assert "Car query: C5 Corvette Z06" in message
    assert "Keywords: manual, z06" in message
    assert "Excluded: automatic" in message
    assert "Notify: `21:45` `Australia/Sydney`" in message
    assert "Delivery: guild `111` | channel `222` | thread `none`" in message
    assert "Sources: `1` active / `1` total" in message
    assert "`#9` **AutoTempest** (`autotempest`, autotempest.com, enabled)" in message


def test_watch_edit_result_distinguishes_changed_and_unchanged() -> None:
    details = WatchDetails(
        watch_id=7,
        name="C5 Z06 hunt",
        car_query="C5 Corvette Z06",
        keywords=["manual", "z06"],
        exclude_keywords=[],
        notify_time="21:45",
        timezone="UTC",
        preferred_currency="USD",
        distance_unit="mi",
        guild_id=None,
        channel_id=None,
        thread_id=None,
        criteria_version=2,
        is_active=False,
        active_sources_count=0,
        sources=[],
    )

    updated_message = _format_watch_edit_result(
        WatchUpdateResult(details=details, changed_fields=["watch_name", "active"])
    )
    unchanged_message = _format_watch_edit_result(
        WatchUpdateResult(details=details, changed_fields=[])
    )

    assert "**Watch updated**" in updated_message
    assert "Changed: `watch_name, active`" in updated_message
    assert "**Watch unchanged**" in unchanged_message
    assert "No editable fields changed." in unchanged_message
