"""Tests for local Discord command registration."""

from car_watch_bot.bot.client import create_bot_client
from car_watch_bot.config import Settings
from car_watch_bot.services.listing_service import ListingService
from car_watch_bot.services.source_service import SourceService
from car_watch_bot.services.watch_service import WatchService


def test_create_bot_client_registers_expected_commands(db_session_factory) -> None:
    settings = Settings(DISCORD_BOT_TOKEN="", DISCORD_GUILD_ID=None)
    watch_service = WatchService(db_session_factory)
    source_service = SourceService(db_session_factory)
    listing_service = ListingService(
        db_session_factory,
        scraper_adapters={},
        usd_to_aud_rate=settings.usd_to_aud_rate,
    )

    client = create_bot_client(settings, watch_service, source_service, listing_service)

    command_names = {command.name for command in client.command_tree.get_commands()}
    assert command_names == {
        "ping",
        "watch_add",
        "watch_currency",
        "watch_distance_unit",
        "watch_exclude_add",
        "watch_exclude_remove",
        "watch_keyword_add",
        "watch_keyword_remove",
        "watch_list",
        "watch_notify_time",
        "watch_remove",
        "watch_scrape_now",
        "watch_listings",
        "watch_source_add",
        "watch_source_list",
        "watch_source_remove",
        "watch_source_remove_menu",
        "watch_source_test",
    }

    commands_by_name = {
        command.name: command for command in client.command_tree.get_commands()
    }
    watch_id_commands = {
        "watch_currency",
        "watch_distance_unit",
        "watch_exclude_add",
        "watch_exclude_remove",
        "watch_keyword_add",
        "watch_keyword_remove",
        "watch_listings",
        "watch_notify_time",
        "watch_remove",
        "watch_scrape_now",
        "watch_source_add",
        "watch_source_list",
        "watch_source_remove",
        "watch_source_remove_menu",
    }
    for command_name in watch_id_commands:
        assert commands_by_name[command_name]._params["watch_id"].autocomplete is not None
    assert (
        commands_by_name["watch_source_remove"]
        ._params["source_id"]
        .autocomplete
        is not None
    )
