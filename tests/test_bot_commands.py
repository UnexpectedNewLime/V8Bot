"""Tests for Discord command formatting helpers."""

import asyncio
from types import SimpleNamespace

import pytest

from car_watch_bot.bot.commands import (
    SourceBatchAddResult,
    _format_sources_added,
    _parse_source_urls,
    _source_id_autocomplete_choices,
    _source_remove_options,
    _split_discord_message,
    _truncate_discord_label,
    _validate_source_name_usage,
    _watch_id_autocomplete_choices,
)
from car_watch_bot.core.models import SourceTestResult
from car_watch_bot.services.source_service import (
    SourceAddResult,
    SourceSummary,
    SourceValidationError,
)
from car_watch_bot.services.watch_service import WatchService


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
