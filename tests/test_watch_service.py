"""Tests for watch service command-facing behaviour."""

import pytest

from car_watch_bot.services.watch_service import (
    WatchNotFoundError,
    WatchService,
    WatchValidationError,
    parse_keyword_csv,
    parse_notify_time,
)


def test_parse_keyword_csv_trims_and_drops_empty_values() -> None:
    keywords = parse_keyword_csv(" manual, HUD, , targa ")

    assert keywords == ["manual", "HUD", "targa"]


def test_parse_keyword_csv_allows_optional_empty_exclusions() -> None:
    keywords = parse_keyword_csv("", allow_empty=True)

    assert keywords == []


def test_parse_notify_time_requires_hh_mm() -> None:
    with pytest.raises(WatchValidationError):
        parse_notify_time("9:30")


def test_watch_service_create_watch_uses_defaults(db_session_factory) -> None:
    service = WatchService(db_session_factory)

    summary = service.create_watch(
        discord_user_id="123",
        car_query="C5 Corvette",
        keywords="manual, HUD, targa",
        exclude_keywords="automatic, convertible",
        notify_time="09:30",
    )

    assert summary.watch_id == 1
    assert summary.car_query == "C5 Corvette"
    assert summary.keywords == ["manual", "HUD", "targa"]
    assert summary.exclude_keywords == ["automatic", "convertible"]
    assert summary.notify_time == "09:30"
    assert summary.preferred_currency == "AUD"
    assert summary.distance_unit == "km"
    assert summary.filters.is_empty()


def test_watch_service_delivery_target_and_thread_update(db_session_factory) -> None:
    service = WatchService(db_session_factory)
    summary = service.create_watch(
        discord_user_id="123",
        car_query="C5 Corvette",
        keywords="manual, HUD",
        exclude_keywords="",
        notify_time="09:30",
        channel_id="999",
    )

    target = service.get_delivery_target("123", summary.watch_id)
    updated_target = service.set_thread_id("123", summary.watch_id, "555")

    assert target.channel_id == "999"
    assert target.thread_id is None
    assert updated_target.thread_id == "555"
    assert service.get_delivery_target("123", summary.watch_id).thread_id == "555"


def test_watch_service_list_watches(db_session_factory) -> None:
    service = WatchService(db_session_factory)
    service.create_watch(
        discord_user_id="123",
        car_query="C5 Corvette",
        keywords="manual",
        exclude_keywords="",
        notify_time="09:30",
    )

    summaries = service.list_watches("123")

    assert len(summaries) == 1
    assert summaries[0].car_query == "C5 Corvette"


def test_watch_service_create_watch_persists_filters(db_session_factory) -> None:
    service = WatchService(db_session_factory)

    summary = service.create_watch(
        discord_user_id="123",
        car_query="C5 Corvette",
        keywords="manual",
        exclude_keywords="",
        notify_time="09:30",
        price_min=20000,
        price_max=45000,
        year_min=2001,
        year_max=2004,
        mileage_max=120000,
        transmission="manual",
        location="Sydney",
        radius=50,
        body_style="coupe",
        must_have="HUD, targa",
    )
    summaries = service.list_watches("123")

    assert summary.filters.price_min is not None
    assert summary.filters.price_min == 20000
    assert summary.filters.must_have_terms == ("HUD", "targa")
    assert summaries[0].filters == summary.filters


def test_watch_service_update_filters_and_clear_fields(db_session_factory) -> None:
    service = WatchService(db_session_factory)
    summary = service.create_watch(
        discord_user_id="123",
        car_query="C5 Corvette",
        keywords="manual",
        exclude_keywords="",
        notify_time="09:30",
        price_max=40000,
        body_style="coupe",
    )

    updated = service.update_filters(
        "123",
        summary.watch_id,
        year_min=2001,
        must_have="HUD",
        clear_fields="body_style",
    )

    assert updated.filters.price_max == 40000
    assert updated.filters.year_min == 2001
    assert updated.filters.body_style is None
    assert updated.filters.must_have_terms == ("HUD",)


def test_watch_service_rejects_invalid_structured_filters(db_session_factory) -> None:
    service = WatchService(db_session_factory)

    with pytest.raises(WatchValidationError, match="year_min"):
        service.create_watch(
            discord_user_id="123",
            car_query="C5 Corvette",
            keywords="manual",
            exclude_keywords="",
            notify_time="09:30",
            year_min=2004,
            year_max=2001,
        )


def test_watch_service_deactivate_watch_checks_ownership(db_session_factory) -> None:
    service = WatchService(db_session_factory)
    summary = service.create_watch(
        discord_user_id="123",
        car_query="C5 Corvette",
        keywords="manual",
        exclude_keywords=None,
        notify_time="09:30",
    )

    with pytest.raises(WatchNotFoundError):
        service.deactivate_watch("456", summary.watch_id)

    service.deactivate_watch("123", summary.watch_id)

    assert service.list_watches("123") == []
