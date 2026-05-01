"""Tests for watch service command-facing behaviour."""

import pytest

from car_watch_bot.db.repositories import SourceRepository
from car_watch_bot.services.watch_service import (
    WatchNotFoundError,
    WatchService,
    WatchUpdateRequest,
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


def test_watch_service_get_watch_details_includes_inactive_and_sources(
    db_session_factory,
) -> None:
    service = WatchService(db_session_factory)
    summary = service.create_watch(
        discord_user_id="123",
        car_query="C5 Corvette",
        keywords="manual",
        exclude_keywords="automatic",
        notify_time="09:30",
        guild_id="111",
        channel_id="222",
    )
    with db_session_factory() as session:
        source = SourceRepository(session).create_source(
            name="AutoTempest",
            kind="autotempest",
            base_url="https://www.autotempest.com/results?make=chevrolet",
        )
        source_id = source.id
        session.commit()

    service.add_source_to_watch("123", summary.watch_id, source_id)
    service.deactivate_watch("123", summary.watch_id)

    details = service.get_watch_details("123", summary.watch_id)

    assert details.watch_id == summary.watch_id
    assert details.name == "C5 Corvette"
    assert details.car_query == "C5 Corvette"
    assert details.keywords == ["manual"]
    assert details.exclude_keywords == ["automatic"]
    assert details.notify_time == "09:30"
    assert details.timezone == "Australia/Sydney"
    assert details.guild_id == "111"
    assert details.channel_id == "222"
    assert details.is_active is False
    assert details.active_sources_count == 1
    assert details.sources[0].name == "AutoTempest"


def test_watch_service_update_watch_edits_full_surface_and_restores_active(
    db_session_factory,
) -> None:
    service = WatchService(db_session_factory)
    summary = service.create_watch(
        discord_user_id="123",
        car_query="C5 Corvette",
        keywords="manual",
        exclude_keywords="automatic",
        notify_time="09:30",
        guild_id="111",
        channel_id="222",
    )

    result = service.update_watch(
        "123",
        summary.watch_id,
        WatchUpdateRequest(
            name="C5 Z06 hunt",
            car_query="C5 Corvette Z06",
            keywords="manual, z06, coupe",
            exclude_keywords="automatic, salvage",
            notify_time="21:45",
            timezone="UTC",
            currency="usd",
            distance_unit="mi",
            guild_id="333",
            channel_id="444",
            thread_id="555",
            is_active=False,
        ),
    )

    assert result.changed_fields == [
        "watch_name",
        "car_query",
        "keywords",
        "excluded_keywords",
        "notify_time",
        "timezone",
        "currency",
        "distance_unit",
        "guild_id",
        "channel_id",
        "thread_id",
        "active",
    ]
    assert result.details.name == "C5 Z06 hunt"
    assert result.details.car_query == "C5 Corvette Z06"
    assert result.details.keywords == ["manual", "z06", "coupe"]
    assert result.details.exclude_keywords == ["automatic", "salvage"]
    assert result.details.notify_time == "21:45"
    assert result.details.timezone == "UTC"
    assert result.details.preferred_currency == "USD"
    assert result.details.distance_unit == "mi"
    assert result.details.guild_id == "333"
    assert result.details.channel_id == "444"
    assert result.details.thread_id == "555"
    assert result.details.criteria_version == 2
    assert result.details.is_active is False
    assert service.list_watches("123") == []

    restored = service.update_watch(
        "123",
        summary.watch_id,
        WatchUpdateRequest(is_active=True),
    )

    assert restored.changed_fields == ["active"]
    assert restored.details.is_active is True
    assert len(service.list_watches("123")) == 1


def test_watch_service_update_watch_can_clear_optional_fields(db_session_factory) -> None:
    service = WatchService(db_session_factory)
    summary = service.create_watch(
        discord_user_id="123",
        car_query="C5 Corvette",
        keywords="manual",
        exclude_keywords="automatic",
        notify_time="09:30",
        channel_id="222",
    )
    service.set_thread_id("123", summary.watch_id, "555")

    result = service.update_watch(
        "123",
        summary.watch_id,
        WatchUpdateRequest(clear_exclusions=True, clear_channel=True),
    )

    assert result.changed_fields == ["excluded_keywords", "channel_id", "thread_id"]
    assert result.details.exclude_keywords == []
    assert result.details.channel_id is None
    assert result.details.thread_id is None
    assert result.details.criteria_version == 2


def test_watch_service_update_watch_validates_without_persisting_partial_changes(
    db_session_factory,
) -> None:
    service = WatchService(db_session_factory)
    summary = service.create_watch(
        discord_user_id="123",
        car_query="C5 Corvette",
        keywords="manual",
        exclude_keywords="automatic",
        notify_time="09:30",
    )

    with pytest.raises(WatchValidationError, match="valid IANA timezone"):
        service.update_watch(
            "123",
            summary.watch_id,
            WatchUpdateRequest(name="New name", timezone="Not/AZone"),
        )

    details = service.get_watch_details("123", summary.watch_id)

    assert details.name == "C5 Corvette"


def test_watch_service_update_watch_requires_channel_for_thread(
    db_session_factory,
) -> None:
    service = WatchService(db_session_factory)
    summary = service.create_watch(
        discord_user_id="123",
        car_query="C5 Corvette",
        keywords="manual",
        exclude_keywords="",
        notify_time="09:30",
    )

    with pytest.raises(WatchValidationError, match="requires a channel_id"):
        service.update_watch(
            "123",
            summary.watch_id,
            WatchUpdateRequest(thread_id="555"),
        )
