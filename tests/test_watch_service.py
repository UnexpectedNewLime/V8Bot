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
