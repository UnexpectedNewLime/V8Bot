"""Discord slash command registration."""

import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import urlparse

import discord
from discord import app_commands

from car_watch_bot.bot.embeds import build_listing_embed
from car_watch_bot.bot.listing_actions import build_listing_action_view
from car_watch_bot.bot.watch_threads import resolve_watch_thread
from car_watch_bot.core.models import DigestListing, ScrapeNowResult, SourceTestResult
from car_watch_bot.services.listing_service import ListingService
from car_watch_bot.services.source_service import (
    SourceAddResult,
    SourceNotFoundError,
    SourceService,
    SourceSummary,
    SourceValidationError,
)
from car_watch_bot.services.watch_service import (
    WatchDetails,
    WatchNotFoundError,
    WatchService,
    WatchSummary,
    WatchUpdateRequest,
    WatchUpdateResult,
    WatchValidationError,
)


logger = logging.getLogger(__name__)
DISCORD_MESSAGE_LIMIT = 2000
DISCORD_SAFE_MESSAGE_LIMIT = 1900
DISCORD_CHOICE_LIMIT = 25
DISCORD_CHOICE_NAME_LIMIT = 100
DISCORD_SELECT_DESCRIPTION_LIMIT = 100
URL_PATTERN = re.compile(r"https?://[^\s<>\]\),]+")
HIDDEN_SOURCE_NOTES = {"skipped Facebook Marketplace source"}


@dataclass(frozen=True)
class SourceBatchAddResult:
    """Result from adding one or more source URLs."""

    added: list[SourceAddResult]
    failed: list[tuple[str, str]]


async def _watch_id_autocomplete_choices(
    interaction: discord.Interaction,
    current: object,
    watch_service: WatchService,
) -> list[app_commands.Choice[int]]:
    """Return user-scoped watch choices for Discord autocomplete."""

    try:
        summaries = watch_service.list_watches(str(interaction.user.id))
    except Exception:
        logger.exception(
            "watch autocomplete failed",
            extra={"discord_user_id": str(interaction.user.id)},
        )
        return []

    normalized_current = _normalize_autocomplete_current(current)
    choices: list[app_commands.Choice[int]] = []
    for summary in summaries:
        search_text = _watch_choice_search_text(summary)
        if normalized_current and normalized_current not in search_text:
            continue
        choices.append(
            app_commands.Choice(
                name=_truncate_discord_label(_format_watch_choice_label(summary)),
                value=summary.watch_id,
            )
        )
        if len(choices) >= DISCORD_CHOICE_LIMIT:
            break
    return choices


async def _source_id_autocomplete_choices(
    interaction: discord.Interaction,
    current: object,
    source_service: SourceService,
) -> list[app_commands.Choice[int]]:
    """Return source choices scoped to the selected owned watch."""

    watch_id = _namespace_int(interaction, "watch_id")
    if watch_id is None:
        return []

    try:
        summaries = source_service.list_sources_for_watch(
            str(interaction.user.id),
            watch_id,
        )
    except (WatchNotFoundError, SourceValidationError):
        return []
    except Exception:
        logger.exception(
            "source autocomplete failed",
            extra={
                "discord_user_id": str(interaction.user.id),
                "watch_id": watch_id,
            },
        )
        return []

    normalized_current = _normalize_autocomplete_current(current)
    choices: list[app_commands.Choice[int]] = []
    for summary in summaries:
        search_text = _source_choice_search_text(summary)
        if normalized_current and normalized_current not in search_text:
            continue
        choices.append(
            app_commands.Choice(
                name=_truncate_discord_label(_format_source_choice_label(summary)),
                value=summary.source_id,
            )
        )
        if len(choices) >= DISCORD_CHOICE_LIMIT:
            break
    return choices


class _SourceRemoveSelect(discord.ui.Select):
    """Select menu that removes one source from a watch."""

    def __init__(self, options: list[discord.SelectOption]) -> None:
        super().__init__(
            placeholder="Select source to remove",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, _SourceRemoveView):
            await interaction.response.send_message(
                "source removal menu is no longer available",
                ephemeral=True,
            )
            return
        if str(interaction.user.id) != view.discord_user_id:
            await interaction.response.send_message(
                "this source removal menu belongs to another user",
                ephemeral=True,
            )
            return

        source_id = int(self.values[0])
        source_name = view.source_names_by_id.get(source_id, f"source {source_id}")
        try:
            view.source_service.remove_source_from_watch(
                view.discord_user_id,
                view.watch_id,
                source_id,
            )
        except WatchNotFoundError:
            await interaction.response.edit_message(
                content="watch not found or not owned by you",
                view=None,
            )
            view.stop()
            return
        except SourceNotFoundError:
            await interaction.response.edit_message(
                content="source not found for watch",
                view=None,
            )
            view.stop()
            return
        except Exception:
            logger.exception(
                "source removal menu failed",
                extra={
                    "discord_user_id": view.discord_user_id,
                    "watch_id": view.watch_id,
                    "source_id": source_id,
                },
            )
            await interaction.response.edit_message(
                content="failed to remove source",
                view=None,
            )
            view.stop()
            return

        await interaction.response.edit_message(
            content=f"source #{source_id} {source_name} removed from watch {view.watch_id}",
            view=None,
        )
        view.stop()


class _SourceRemoveView(discord.ui.View):
    """Ephemeral source removal view."""

    def __init__(
        self,
        source_service: SourceService,
        discord_user_id: str,
        watch_id: int,
        summaries: list[SourceSummary],
    ) -> None:
        super().__init__(timeout=180)
        self.source_service = source_service
        self.discord_user_id = discord_user_id
        self.watch_id = watch_id
        self.source_names_by_id = {
            summary.source_id: summary.name for summary in summaries
        }
        self.add_item(_SourceRemoveSelect(_source_remove_options(summaries)))


def register_commands(
    command_tree: app_commands.CommandTree[discord.Client],
    watch_service: WatchService,
    source_service: SourceService,
    listing_service: ListingService,
) -> None:
    """Register supported slash commands."""

    async def watch_id_autocomplete(
        interaction: discord.Interaction,
        current: object,
    ) -> list[app_commands.Choice[int]]:
        return await _watch_id_autocomplete_choices(
            interaction,
            current,
            watch_service,
        )

    async def source_id_autocomplete(
        interaction: discord.Interaction,
        current: object,
    ) -> list[app_commands.Choice[int]]:
        return await _source_id_autocomplete_choices(
            interaction,
            current,
            source_service,
        )

    @command_tree.command(name="ping", description="Check whether the bot is responsive.")
    async def ping(interaction: discord.Interaction) -> None:
        await interaction.response.send_message("pong")

    @command_tree.command(name="watch_add", description="Add a car listing watch.")
    async def watch_add(
        interaction: discord.Interaction,
        car_query: str,
        keywords: str,
        notify_time: str,
        exclude_keywords: str = "",
        source_url: str = "",
        source_name: str = "",
        scrape_now: bool = True,
    ) -> None:
        async def action() -> str:
            summary = watch_service.create_watch(
                discord_user_id=str(interaction.user.id),
                car_query=car_query,
                keywords=keywords,
                exclude_keywords=exclude_keywords,
                notify_time=notify_time,
                guild_id=str(interaction.guild_id) if interaction.guild_id else None,
                channel_id=str(interaction.channel_id) if interaction.channel_id else None,
            )
            source_urls = _parse_source_urls(source_url)
            _validate_source_name_usage(source_name, source_urls)
            logger.info(
                "watch_add created watch_id=%s user_id=%s source_url_count=%s scrape_now=%s",
                summary.watch_id,
                interaction.user.id,
                len(source_urls),
                scrape_now,
            )
            if not source_urls:
                return _format_watch_created(summary)

            source_results = await _add_sources_to_watch(
                source_service=source_service,
                discord_user_id=str(interaction.user.id),
                watch_id=summary.watch_id,
                urls=source_urls,
                name=source_name,
            )
            scrape_result: ScrapeNowResult | None = None
            listings: list[DigestListing] = []
            if scrape_now and source_results.added:
                scrape_result = await listing_service.scrape_watch_now(
                    str(interaction.user.id),
                    summary.watch_id,
                )
                listings = listing_service.list_watch_listings(
                    str(interaction.user.id),
                    summary.watch_id,
                    listing_ids=scrape_result.new_listing_ids,
                )
                await _send_public_listing_embeds(
                    interaction,
                    watch_service,
                    str(interaction.user.id),
                    summary.watch_id,
                    listings,
                    heading=f"{summary.car_query}: {len(listings)} new listings",
                    empty_message=(
                        f"{summary.car_query}: scrape complete, no new listings."
                    ),
                )
                listing_service.mark_watch_listings_sent(
                    str(interaction.user.id),
                    summary.watch_id,
                    scrape_result.new_listing_ids,
                )
            logger.info(
                "watch_add sources processed watch_id=%s user_id=%s added=%s failed=%s scraped=%s",
                summary.watch_id,
                interaction.user.id,
                len(source_results.added),
                len(source_results.failed),
                scrape_result is not None,
            )
            return _format_watch_created_with_sources(
                summary,
                source_results,
                scrape_result,
            )

        await _send_ephemeral_result(interaction, action, "failed to create watch")

    @command_tree.command(name="watch_list", description="List your active watches.")
    async def watch_list(interaction: discord.Interaction) -> None:
        async def action() -> str:
            summaries = watch_service.list_watches(str(interaction.user.id))
            if not summaries:
                return "no active watches"
            return _format_watch_list(summaries)

        await _send_ephemeral_result(interaction, action, "failed to list watches")

    @command_tree.command(name="watch_show", description="Show one watch in detail.")
    @app_commands.autocomplete(watch_id=watch_id_autocomplete)
    async def watch_show(interaction: discord.Interaction, watch_id: int) -> None:
        async def action() -> str:
            details = watch_service.get_watch_details(str(interaction.user.id), watch_id)
            return _format_watch_details(details)

        await _send_ephemeral_result(interaction, action, "failed to show watch")

    @command_tree.command(name="watch_edit", description="Edit one of your watches.")
    @app_commands.autocomplete(watch_id=watch_id_autocomplete)
    async def watch_edit(
        interaction: discord.Interaction,
        watch_id: int,
        car_query: str = "",
        watch_name: str = "",
        keywords: str = "",
        exclude_keywords: str = "",
        clear_exclusions: bool = False,
        notify_time: str = "",
        timezone: str = "",
        currency: str = "",
        distance_unit: str = "",
        channel_id: str = "",
        thread_id: str = "",
        clear_channel: bool = False,
        clear_thread: bool = False,
        use_current_channel: bool = False,
        active: bool | None = None,
    ) -> None:
        async def action() -> str:
            if use_current_channel and channel_id.strip():
                raise WatchValidationError(
                    "channel_id cannot be set when use_current_channel is true"
                )
            current_channel_id = (
                str(interaction.channel_id)
                if use_current_channel and interaction.channel_id
                else None
            )
            current_guild_id = (
                str(interaction.guild_id)
                if use_current_channel and interaction.guild_id
                else None
            )
            result = watch_service.update_watch(
                str(interaction.user.id),
                watch_id,
                WatchUpdateRequest(
                    name=_optional_command_text(watch_name),
                    car_query=_optional_command_text(car_query),
                    keywords=_optional_command_text(keywords),
                    exclude_keywords=_optional_command_text(exclude_keywords),
                    clear_exclusions=clear_exclusions,
                    notify_time=_optional_command_text(notify_time),
                    timezone=_optional_command_text(timezone),
                    currency=_optional_command_text(currency),
                    distance_unit=_optional_command_text(distance_unit),
                    guild_id=current_guild_id,
                    channel_id=current_channel_id or _optional_command_text(channel_id),
                    thread_id=_optional_command_text(thread_id),
                    clear_channel=clear_channel,
                    clear_thread=clear_thread,
                    is_active=active,
                ),
            )
            logger.info(
                "watch_edit completed watch_id=%s user_id=%s changed_fields=%s",
                watch_id,
                interaction.user.id,
                ",".join(result.changed_fields) or "none",
            )
            return _format_watch_edit_result(result)

        await _send_ephemeral_result(interaction, action, "failed to edit watch")

    @command_tree.command(name="watch_scrape_now", description="Scrape one watch now.")
    @app_commands.autocomplete(watch_id=watch_id_autocomplete)
    async def watch_scrape_now(interaction: discord.Interaction, watch_id: int) -> None:
        async def action() -> str:
            result = await listing_service.scrape_watch_now(
                str(interaction.user.id),
                watch_id,
            )
            logger.info(
                "watch_scrape_now completed watch_id=%s user_id=%s sources_seen=%s sources_scraped=%s listings_created=%s pending=%s",
                watch_id,
                interaction.user.id,
                result.sources_seen,
                result.sources_scraped,
                result.listings_created,
                result.pending_listings,
            )
            listings = listing_service.list_watch_listings(
                str(interaction.user.id),
                watch_id,
                listing_ids=result.new_listing_ids,
            )
            await _send_public_listing_embeds(
                interaction,
                watch_service,
                str(interaction.user.id),
                watch_id,
                listings,
                heading=f"Watch {watch_id}: {len(listings)} new listings",
                empty_message=f"Watch {watch_id}: scrape complete, no new listings.",
            )
            listing_service.mark_watch_listings_sent(
                str(interaction.user.id),
                watch_id,
                result.new_listing_ids,
            )
            return "\n".join(
                [
                    _format_scrape_now_result(result),
                    f"posted new listing messages: {len(listings)}",
                ]
            )

        await _send_ephemeral_result(interaction, action, "failed to scrape watch")

    @command_tree.command(name="watch_listings", description="Show pending watch listings.")
    @app_commands.autocomplete(watch_id=watch_id_autocomplete)
    async def watch_listings(interaction: discord.Interaction, watch_id: int) -> None:
        async def action() -> str:
            listings = listing_service.list_watch_listings(str(interaction.user.id), watch_id)
            if not listings:
                return f"watch {watch_id} has no pending listings"
            await _send_public_listing_embeds(
                interaction,
                watch_service,
                str(interaction.user.id),
                watch_id,
                listings,
                heading=f"Watch {watch_id}: {len(listings)} pending listings",
            )
            return f"posted {len(listings)} listing messages for watch {watch_id}"

        await _send_ephemeral_result(interaction, action, "failed to list watch listings")

    @command_tree.command(name="watch_remove", description="Remove one of your watches.")
    @app_commands.autocomplete(watch_id=watch_id_autocomplete)
    async def watch_remove(interaction: discord.Interaction, watch_id: int) -> None:
        async def action() -> str:
            watch_service.deactivate_watch(str(interaction.user.id), watch_id)
            return f"watch {watch_id} deactivated"

        await _send_ephemeral_result(interaction, action, "failed to remove watch")

    @command_tree.command(name="watch_keyword_add", description="Add a watch keyword.")
    @app_commands.autocomplete(watch_id=watch_id_autocomplete)
    async def watch_keyword_add(
        interaction: discord.Interaction,
        watch_id: int,
        keyword: str,
    ) -> None:
        async def action() -> str:
            summary = watch_service.add_keyword(str(interaction.user.id), watch_id, keyword)
            return _format_watch_updated("keyword added", summary)

        await _send_ephemeral_result(interaction, action, "failed to add keyword")

    @command_tree.command(name="watch_keyword_remove", description="Remove a watch keyword.")
    @app_commands.autocomplete(watch_id=watch_id_autocomplete)
    async def watch_keyword_remove(
        interaction: discord.Interaction,
        watch_id: int,
        keyword: str,
    ) -> None:
        async def action() -> str:
            summary = watch_service.remove_keyword(
                str(interaction.user.id),
                watch_id,
                keyword,
            )
            return _format_watch_updated("keyword removed", summary)

        await _send_ephemeral_result(interaction, action, "failed to remove keyword")

    @command_tree.command(name="watch_exclude_add", description="Add an excluded keyword.")
    @app_commands.autocomplete(watch_id=watch_id_autocomplete)
    async def watch_exclude_add(
        interaction: discord.Interaction,
        watch_id: int,
        keyword: str,
    ) -> None:
        async def action() -> str:
            summary = watch_service.add_exclude_keyword(
                str(interaction.user.id),
                watch_id,
                keyword,
            )
            return _format_watch_updated("exclude keyword added", summary)

        await _send_ephemeral_result(interaction, action, "failed to add exclude keyword")

    @command_tree.command(
        name="watch_exclude_remove",
        description="Remove an excluded keyword.",
    )
    @app_commands.autocomplete(watch_id=watch_id_autocomplete)
    async def watch_exclude_remove(
        interaction: discord.Interaction,
        watch_id: int,
        keyword: str,
    ) -> None:
        async def action() -> str:
            summary = watch_service.remove_exclude_keyword(
                str(interaction.user.id),
                watch_id,
                keyword,
            )
            return _format_watch_updated("exclude keyword removed", summary)

        await _send_ephemeral_result(
            interaction,
            action,
            "failed to remove exclude keyword",
        )

    @command_tree.command(name="watch_source_add", description="Add and test a source.")
    @app_commands.autocomplete(watch_id=watch_id_autocomplete)
    async def watch_source_add(
        interaction: discord.Interaction,
        watch_id: int,
        url: str,
        name: str = "",
    ) -> None:
        async def action() -> str:
            urls = _parse_source_urls(url)
            _validate_source_name_usage(name, urls)
            logger.info(
                "watch_source_add request watch_id=%s user_id=%s url_count=%s explicit_name=%s",
                watch_id,
                interaction.user.id,
                len(urls),
                bool(name.strip()),
            )
            result = await _add_sources_to_watch(
                source_service=source_service,
                discord_user_id=str(interaction.user.id),
                watch_id=watch_id,
                urls=urls,
                name=name,
            )
            logger.info(
                "watch_source_add completed watch_id=%s user_id=%s added=%s failed=%s",
                watch_id,
                interaction.user.id,
                len(result.added),
                len(result.failed),
            )
            return _format_sources_added(result)

        await _send_ephemeral_result(interaction, action, "failed to add source")

    @command_tree.command(name="watch_source_list", description="List watch sources.")
    @app_commands.autocomplete(watch_id=watch_id_autocomplete)
    async def watch_source_list(interaction: discord.Interaction, watch_id: int) -> None:
        async def action() -> str:
            summaries = source_service.list_sources_for_watch(
                str(interaction.user.id),
                watch_id,
            )
            if not summaries:
                return f"watch {watch_id} has no active sources"
            return _format_source_list(watch_id, summaries)

        await _send_ephemeral_result(interaction, action, "failed to list sources")

    @command_tree.command(name="watch_source_remove", description="Remove a watch source.")
    @app_commands.autocomplete(
        watch_id=watch_id_autocomplete,
        source_id=source_id_autocomplete,
    )
    async def watch_source_remove(
        interaction: discord.Interaction,
        watch_id: int,
        source_id: int,
    ) -> None:
        async def action() -> str:
            source_service.remove_source_from_watch(
                str(interaction.user.id),
                watch_id,
                source_id,
            )
            return f"source {source_id} removed from watch {watch_id}"

        await _send_ephemeral_result(interaction, action, "failed to remove source")

    @command_tree.command(
        name="watch_source_remove_menu",
        description="Pick a watch source to remove.",
    )
    @app_commands.autocomplete(watch_id=watch_id_autocomplete)
    async def watch_source_remove_menu(
        interaction: discord.Interaction,
        watch_id: int,
    ) -> None:
        await _send_source_remove_menu(
            interaction=interaction,
            source_service=source_service,
            watch_id=watch_id,
        )

    @command_tree.command(name="watch_source_test", description="Test a source URL.")
    async def watch_source_test(interaction: discord.Interaction, url: str) -> None:
        async def action() -> str:
            result = await source_service.test_source_url(str(interaction.user.id), url)
            logger.info(
                "watch_source_test completed user_id=%s accepted=%s listings_found=%s warnings=%s errors=%s domain=%s",
                interaction.user.id,
                result.url_accepted,
                result.listings_found,
                len(result.warnings),
                len(result.errors),
                _source_domain(url),
            )
            return _format_source_test(result)

        await _send_ephemeral_result(interaction, action, "failed to test source")

    @command_tree.command(name="watch_notify_time", description="Update notify time.")
    @app_commands.autocomplete(watch_id=watch_id_autocomplete)
    async def watch_notify_time(
        interaction: discord.Interaction,
        watch_id: int,
        notify_time: str,
    ) -> None:
        async def action() -> str:
            summary = watch_service.update_notify_time(
                str(interaction.user.id),
                watch_id,
                notify_time,
            )
            return _format_watch_updated("notify time updated", summary)

        await _send_ephemeral_result(interaction, action, "failed to update notify time")

    @command_tree.command(name="watch_currency", description="Update watch currency.")
    @app_commands.autocomplete(watch_id=watch_id_autocomplete)
    async def watch_currency(
        interaction: discord.Interaction,
        watch_id: int,
        currency: str,
    ) -> None:
        async def action() -> str:
            summary = watch_service.update_currency(
                str(interaction.user.id),
                watch_id,
                currency,
            )
            return _format_watch_updated("currency updated", summary)

        await _send_ephemeral_result(interaction, action, "failed to update currency")

    @command_tree.command(
        name="watch_distance_unit",
        description="Update watch distance unit.",
    )
    @app_commands.autocomplete(watch_id=watch_id_autocomplete)
    async def watch_distance_unit(
        interaction: discord.Interaction,
        watch_id: int,
        distance_unit: str,
    ) -> None:
        async def action() -> str:
            summary = watch_service.update_distance_unit(
                str(interaction.user.id),
                watch_id,
                distance_unit,
            )
            return _format_watch_updated("distance unit updated", summary)

        await _send_ephemeral_result(
            interaction,
            action,
            "failed to update distance unit",
        )


async def _send_ephemeral_result(
    interaction: discord.Interaction,
    action: Callable[[], Awaitable[str]],
    fallback_message: str,
) -> None:
    """Run a command action and send an ephemeral response."""

    command_name = interaction.command.name if interaction.command else "unknown"
    logger.info(
        "discord command start command=%s user_id=%s guild_id=%s channel_id=%s",
        command_name,
        interaction.user.id,
        interaction.guild_id,
        interaction.channel_id,
    )
    await interaction.response.defer(ephemeral=True)
    try:
        message = await action()
    except (WatchValidationError, SourceValidationError) as exc:
        logger.info(
            "discord command validation failed command=%s user_id=%s error=%s",
            command_name,
            interaction.user.id,
            exc,
        )
        await _send_ephemeral_message(interaction, str(exc))
        return
    except WatchNotFoundError:
        logger.info(
            "discord command watch not found command=%s user_id=%s",
            command_name,
            interaction.user.id,
        )
        await _send_ephemeral_message(interaction, "watch not found or not owned by you")
        return
    except SourceNotFoundError:
        logger.info(
            "discord command source not found command=%s user_id=%s",
            command_name,
            interaction.user.id,
        )
        await _send_ephemeral_message(interaction, "source not found for watch")
        return
    except Exception:
        logger.exception(
            "discord command failed command=%s user_id=%s",
            command_name,
            interaction.user.id,
        )
        await _send_ephemeral_message(interaction, fallback_message)
        return

    logger.info(
        "discord command success command=%s user_id=%s response_chars=%s",
        command_name,
        interaction.user.id,
        len(message),
    )
    await _send_ephemeral_message(interaction, message)


async def _send_source_remove_menu(
    *,
    interaction: discord.Interaction,
    source_service: SourceService,
    watch_id: int,
) -> None:
    """Send an ephemeral source removal select menu."""

    command_name = interaction.command.name if interaction.command else "unknown"
    logger.info(
        "discord command start command=%s user_id=%s guild_id=%s channel_id=%s",
        command_name,
        interaction.user.id,
        interaction.guild_id,
        interaction.channel_id,
    )
    await interaction.response.defer(ephemeral=True)
    try:
        summaries = source_service.list_sources_for_watch(
            str(interaction.user.id),
            watch_id,
        )
    except WatchNotFoundError:
        logger.info(
            "discord command watch not found command=%s user_id=%s",
            command_name,
            interaction.user.id,
        )
        await _send_ephemeral_message(interaction, "watch not found or not owned by you")
        return
    except SourceValidationError as exc:
        logger.info(
            "discord command validation failed command=%s user_id=%s error=%s",
            command_name,
            interaction.user.id,
            exc,
        )
        await _send_ephemeral_message(interaction, str(exc))
        return
    except Exception:
        logger.exception(
            "discord command failed command=%s user_id=%s",
            command_name,
            interaction.user.id,
        )
        await _send_ephemeral_message(interaction, "failed to prepare source removal menu")
        return

    if not summaries:
        await _send_ephemeral_message(
            interaction,
            f"watch {watch_id} has no active sources to remove",
        )
        return

    visible_count = min(len(summaries), DISCORD_CHOICE_LIMIT)
    suffix = ""
    if len(summaries) > DISCORD_CHOICE_LIMIT:
        suffix = f" Showing first {DISCORD_CHOICE_LIMIT} sources."
    view = _SourceRemoveView(
        source_service=source_service,
        discord_user_id=str(interaction.user.id),
        watch_id=watch_id,
        summaries=summaries[:DISCORD_CHOICE_LIMIT],
    )
    await interaction.followup.send(
        (
            f"Select a source to remove from watch {watch_id} "
            f"({visible_count} available).{suffix}"
        ),
        view=view,
        ephemeral=True,
    )
    logger.info(
        "discord command success command=%s user_id=%s source_options=%s",
        command_name,
        interaction.user.id,
        visible_count,
    )


async def _send_ephemeral_message(
    interaction: discord.Interaction,
    message: str,
) -> None:
    """Send a possibly long ephemeral response in Discord-safe chunks."""

    for chunk in _split_discord_message(message):
        await interaction.followup.send(chunk, ephemeral=True)


async def _send_public_listing_embeds(
    interaction: discord.Interaction,
    watch_service: WatchService,
    discord_user_id: str,
    watch_id: int,
    listings: list[DigestListing],
    heading: str,
    empty_message: str | None = None,
) -> None:
    """Send each listing as its own public message in the watch thread."""

    target = watch_service.get_delivery_target(discord_user_id, watch_id)
    thread = await resolve_watch_thread(interaction.client, target)
    resolved_thread_id = str(thread.id)
    if not listings:
        if empty_message:
            await thread.send(content=empty_message, silent=True)
            if resolved_thread_id != target.thread_id:
                watch_service.set_thread_id(discord_user_id, watch_id, resolved_thread_id)
        return
    if resolved_thread_id != target.thread_id:
        watch_service.set_thread_id(discord_user_id, watch_id, resolved_thread_id)
    for listing in listings:
        await thread.send(
            embed=build_listing_embed(
                listing=listing,
                heading=heading,
                query=target.watch_query,
            ),
            view=build_listing_action_view(watch_id, listing.listing_id),
            silent=True,
        )


def _parse_source_urls(raw_urls: str) -> list[str]:
    """Parse one or more source URLs from a command field."""

    urls: list[str] = []
    seen_urls: set[str] = set()
    for match in URL_PATTERN.finditer(raw_urls):
        url = match.group(0).rstrip(".,;")
        if url and url not in seen_urls:
            urls.append(url)
            seen_urls.add(url)
    return urls


def _validate_source_name_usage(name: str, urls: list[str]) -> None:
    """Validate optional source name usage."""

    if not urls:
        return
    if len(urls) > 1 and name.strip():
        raise SourceValidationError("name can only be used with a single URL")


async def _add_sources_to_watch(
    *,
    source_service: SourceService,
    discord_user_id: str,
    watch_id: int,
    urls: list[str],
    name: str,
) -> SourceBatchAddResult:
    """Add many source URLs and collect per-URL failures."""

    if not urls:
        raise SourceValidationError("source url is required")

    added: list[SourceAddResult] = []
    failed: list[tuple[str, str]] = []
    for index, url in enumerate(urls):
        source_name = name if index == 0 else ""
        try:
            result = await source_service.add_source_to_watch(
                discord_user_id=discord_user_id,
                watch_id=watch_id,
                name=source_name,
                url=url,
            )
            added.append(result)
            logger.info(
                "source add succeeded watch_id=%s source_id=%s kind=%s domain=%s listings_found=%s",
                watch_id,
                result.source.source_id,
                result.source.kind,
                _source_domain(url),
                result.source_test.listings_found,
            )
        except SourceValidationError as exc:
            failed.append((url, str(exc)))
            logger.info(
                "source add failed watch_id=%s domain=%s error=%s",
                watch_id,
                _source_domain(url),
                exc,
            )
    return SourceBatchAddResult(added=added, failed=failed)


def _split_discord_message(message: str) -> list[str]:
    """Split text into chunks below Discord's content limit."""

    if len(message) <= DISCORD_MESSAGE_LIMIT:
        return [message]

    chunks: list[str] = []
    current_lines: list[str] = []
    current_length = 0
    for line in message.splitlines():
        line_length = len(line)
        separator_length = 1 if current_lines else 0
        if line_length > DISCORD_SAFE_MESSAGE_LIMIT:
            if current_lines:
                chunks.append("\n".join(current_lines))
                current_lines = []
                current_length = 0
            chunks.extend(_split_long_line(line))
            continue
        if current_length + separator_length + line_length > DISCORD_SAFE_MESSAGE_LIMIT:
            chunks.append("\n".join(current_lines))
            current_lines = [line]
            current_length = line_length
            continue
        current_lines.append(line)
        current_length += separator_length + line_length
    if current_lines:
        chunks.append("\n".join(current_lines))
    return chunks


def _split_long_line(line: str) -> list[str]:
    """Split a single line that exceeds the safe Discord message size."""

    return [
        line[index : index + DISCORD_SAFE_MESSAGE_LIMIT]
        for index in range(0, len(line), DISCORD_SAFE_MESSAGE_LIMIT)
    ]


def _namespace_int(interaction: discord.Interaction, name: str) -> int | None:
    """Read an integer value already chosen for another slash-command option."""

    namespace = getattr(interaction, "namespace", None)
    raw_value = getattr(namespace, name, None)
    if raw_value is None:
        return None
    if isinstance(raw_value, int):
        return raw_value
    value_text = str(raw_value).strip().removeprefix("#")
    if not value_text:
        return None
    try:
        return int(value_text)
    except ValueError:
        return None


def _normalize_autocomplete_current(current: object) -> str:
    """Normalize Discord autocomplete input for case-insensitive matching."""

    if current is None:
        return ""
    return str(current).strip().casefold()


def _watch_choice_search_text(summary: WatchSummary) -> str:
    """Build searchable text for a watch autocomplete choice."""

    return " ".join(
        [
            str(summary.watch_id),
            f"#{summary.watch_id}",
            summary.car_query,
            *summary.keywords,
            *summary.exclude_keywords,
        ]
    ).casefold()


def _source_choice_search_text(summary: SourceSummary) -> str:
    """Build searchable text for a source autocomplete choice."""

    return " ".join(
        [
            str(summary.source_id),
            f"#{summary.source_id}",
            summary.name,
            summary.kind,
            _source_domain(summary.base_url),
            summary.base_url or "",
        ]
    ).casefold()


def _format_watch_choice_label(summary: WatchSummary) -> str:
    """Format a watch autocomplete label."""

    keywords = _comma_list(summary.keywords)
    return (
        f"#{summary.watch_id} {summary.car_query} - "
        f"{keywords} - {summary.active_sources_count} sources"
    )


def _format_source_choice_label(summary: SourceSummary) -> str:
    """Format a source autocomplete label."""

    return (
        f"#{summary.source_id} {summary.name} "
        f"({summary.kind}, {_source_domain(summary.base_url)})"
    )


def _source_remove_options(summaries: list[SourceSummary]) -> list[discord.SelectOption]:
    """Build select-menu options for source removal."""

    return [
        discord.SelectOption(
            label=_truncate_discord_label(f"#{summary.source_id} {summary.name}"),
            value=str(summary.source_id),
            description=_truncate_discord_label(
                f"{summary.kind} - {_source_domain(summary.base_url)}",
                DISCORD_SELECT_DESCRIPTION_LIMIT,
            ),
        )
        for summary in summaries[:DISCORD_CHOICE_LIMIT]
    ]


def _truncate_discord_label(
    value: str,
    limit: int = DISCORD_CHOICE_NAME_LIMIT,
) -> str:
    """Trim a Discord choice/select label to its API limit."""

    compact_value = " ".join(value.split())
    if len(compact_value) <= limit:
        return compact_value
    if limit <= 3:
        return compact_value[:limit]
    return f"{compact_value[: limit - 3].rstrip()}..."


def _format_watch_created(summary: WatchSummary) -> str:
    """Format watch creation confirmation."""

    return "\n".join(
        [
            "**Watch created**",
            f"`#{summary.watch_id}` {summary.car_query}",
            f"Keywords: {_comma_list(summary.keywords)}",
            f"Notify: `{summary.notify_time}`",
            f"Defaults: `{summary.preferred_currency}` / `{summary.distance_unit}`",
        ]
    )


def _format_watch_created_with_sources(
    summary: WatchSummary,
    source_results: SourceBatchAddResult,
    scrape_result: ScrapeNowResult | None,
) -> str:
    """Format one-command watch setup result."""

    sections = [
        _format_watch_created(summary),
        _format_sources_added(source_results),
    ]
    if scrape_result is not None:
        sections.append(_format_scrape_now_result(scrape_result))
    return "\n\n".join(sections)


def _format_watch_updated(action: str, summary: WatchSummary) -> str:
    """Format a watch update response."""

    return "\n".join([action, _format_watch_block(summary)])


def _format_watch_list(summaries: list[WatchSummary]) -> str:
    """Format active watch summaries."""

    return "\n\n".join(_format_watch_block(summary) for summary in summaries)


def _format_watch_details(details: WatchDetails) -> str:
    """Format detailed watch configuration."""

    lines = [
        "**Watch details**",
        f"`#{details.watch_id}` **{details.name}**",
        f"Active: `{_yes_no(details.is_active)}`",
        f"Car query: {details.car_query}",
        f"Keywords: {_comma_list(details.keywords)}",
        f"Excluded: {_comma_list(details.exclude_keywords)}",
        f"Notify: `{details.notify_time}` `{details.timezone}`",
        f"Defaults: `{details.preferred_currency}` / `{details.distance_unit}`",
        (
            "Delivery: "
            f"guild `{_optional_id(details.guild_id)}` | "
            f"channel `{_optional_id(details.channel_id)}` | "
            f"thread `{_optional_id(details.thread_id)}`"
        ),
        f"Criteria version: `{details.criteria_version}`",
        (
            f"Sources: `{details.active_sources_count}` active / "
            f"`{len(details.sources)}` total"
        ),
    ]
    source_lines = _format_watch_source_details(details)
    if source_lines:
        lines.extend(source_lines)
    return "\n".join(lines)


def _format_watch_edit_result(result: WatchUpdateResult) -> str:
    """Format the result of a consolidated watch edit."""

    if result.changed_fields:
        heading = "**Watch updated**"
        changes = f"Changed: `{', '.join(result.changed_fields)}`"
    else:
        heading = "**Watch unchanged**"
        changes = "No editable fields changed."
    return "\n".join([heading, changes, _format_watch_details(result.details)])


def _format_watch_source_details(details: WatchDetails) -> list[str]:
    """Format source rows for watch details."""

    if not details.sources:
        return ["Sources detail: none"]
    lines = ["Sources detail:"]
    for source in details.sources[:10]:
        state = "enabled" if source.is_enabled else "disabled"
        if not source.is_active:
            state = f"{state}, inactive"
        lines.append(
            (
                f"- `#{source.source_id}` **{source.name}** "
                f"(`{source.kind}`, {_source_domain(source.base_url)}, {state})"
            )
        )
    if len(details.sources) > 10:
        lines.append(f"...and {len(details.sources) - 10} more")
    return lines


def _format_watch_block(summary: WatchSummary) -> str:
    """Format one watch summary."""

    exclude_text = _comma_list(summary.exclude_keywords)
    return "\n".join(
        [
            f"`#{summary.watch_id}` **{summary.car_query}**",
            f"Keywords: {_comma_list(summary.keywords)}",
            f"Excluded: {exclude_text}",
            f"Notify: `{summary.notify_time}`",
            f"Defaults: `{summary.preferred_currency}` / `{summary.distance_unit}`",
            f"Sources: `{summary.active_sources_count}`",
        ]
    )


def _format_scrape_now_result(result: ScrapeNowResult) -> str:
    """Format scrape-now result."""

    lines = [
        "**Scrape summary**",
        (
            f"`#{result.watch_id}` sources `{result.sources_scraped}/"
            f"{result.sources_seen}` scraped, skipped `{result.sources_skipped}`"
        ),
        (
            f"New listings: `{result.listings_created}` | "
            f"Pending: `{result.pending_listings}`"
        ),
    ]
    if result.warnings:
        lines.append(f"Warnings: {_comma_list(result.warnings)}")
    return "\n".join(lines)


def _format_watch_listings(watch_id: int, listings: list[DigestListing]) -> str:
    """Format pending listings for a watch."""

    blocks = [_format_digest_listing(listing) for listing in listings[:10]]
    if len(listings) > 10:
        blocks.append(f"...and {len(listings) - 10} more")
    return f"watch_id: {watch_id}\n" + "\n\n".join(blocks)


def _format_digest_listing(listing: DigestListing) -> str:
    """Format one pending listing."""

    reasons = ", ".join(listing.score_reasons) or "none"
    lines = [
        f"listing_id: {listing.listing_id}",
        f"title: {listing.title}",
        f"source: {listing.source_name}",
        f"original price: {listing.original_price}",
        f"converted price: {listing.converted_price}",
        f"original mileage: {listing.original_mileage}",
        f"converted mileage: {listing.converted_mileage}",
    ]
    if listing.price_change:
        lines.append(f"price change: {listing.price_change}")
    if listing.location:
        lines.append(f"location: {listing.location}")
    if listing.first_seen:
        lines.append(f"first seen: {listing.first_seen}")
    if listing.last_seen:
        lines.append(f"last seen: {listing.last_seen}")
    if listing.seller_info:
        lines.append(f"seller info: {listing.seller_info}")
    lines.extend([f"score reasons: {reasons}", f"link: {listing.url}"])
    return "\n".join(lines)


def _comma_list(values: list[str]) -> str:
    """Format a readable comma-separated list."""

    return ", ".join(values) if values else "none"


def _yes_no(value: bool) -> str:
    """Format a bool for Discord text."""

    return "yes" if value else "no"


def _optional_id(value: str | None) -> str:
    """Format an optional Discord id."""

    return value or "none"


def _optional_command_text(value: str) -> str | None:
    """Convert optional Discord command text to a service-layer optional."""

    normalized_value = value.strip()
    return normalized_value or None


def _source_domain(url: str | None) -> str:
    """Return a compact source domain."""

    if not url:
        return "no url"
    host = urlparse(url).netloc.casefold()
    return host.removeprefix("www.") or "unknown domain"


def _format_source_test_summary(result: SourceTestResult) -> str:
    """Format source-test details in one compact row."""

    return (
        f"`{result.listings_found}` listings | "
        f"title {_yes_no(result.title_parsing_worked)} | "
        f"links {_yes_no(result.link_parsing_worked)} | "
        f"price {_yes_no(result.price_parsing_worked)} | "
        f"mileage {_yes_no(result.mileage_parsing_worked)}"
    )


def _format_source_notes(result: SourceTestResult) -> str | None:
    """Format source-test warnings and errors when useful."""

    notes = [
        note
        for note in [*result.warnings, *result.errors]
        if note not in HIDDEN_SOURCE_NOTES
    ]
    if not notes:
        return None
    return f"  Notes: {_comma_list(notes)}"


def _format_source_added_row(result: SourceAddResult) -> str:
    """Format one added source as a compact row."""

    lines = [
        (
            f"- Added `#{result.source.source_id}` **{result.source.name}** "
            f"({result.source.kind}, {_source_domain(result.source.base_url)}): "
            f"{_format_source_test_summary(result.source_test)}"
        )
    ]
    notes = _format_source_notes(result.source_test)
    if notes is not None:
        lines.append(notes)
    return "\n".join(lines)


def _format_source_failure_row(url: str, error: str) -> str:
    """Format one failed source add row."""

    return f"- Not added **{_source_domain(url)}**: {error}"


def _format_source_added(result: SourceAddResult) -> str:
    """Format source add response."""

    return "\n".join(["**Sources**", _format_source_added_row(result)])


def _format_sources_added(result: SourceBatchAddResult) -> str:
    """Format multi-source add response."""

    if not result.added and not result.failed:
        return "**Sources**\nNo sources added"

    lines = [
        "**Sources**",
        (
            f"Added `{len(result.added)}` | "
            f"Not added `{len(result.failed)}`"
        ),
    ]
    lines.extend(_format_source_added_row(source_result) for source_result in result.added)
    lines.extend(_format_source_failure_row(url, error) for url, error in result.failed)
    return "\n".join(lines)


def _format_source_list(watch_id: int, summaries: list[SourceSummary]) -> str:
    """Format sources for a watch."""

    source_blocks = "\n\n".join(_format_source_block(summary) for summary in summaries)
    return f"watch_id: {watch_id}\n{source_blocks}"


def _format_source_block(summary: SourceSummary) -> str:
    """Format one source summary."""

    return "\n".join(
        [
            f"`#{summary.source_id}` **{summary.name}**",
            f"Kind: `{summary.kind}`",
            f"Domain: {_source_domain(summary.base_url)}",
        ]
    )


def _format_source_test(result: SourceTestResult) -> str:
    """Format source test result."""

    status = "Accepted" if result.url_accepted else "Diagnostic only"
    if result.errors:
        status = "Rejected"
    lines = [
        f"**Source test: {status}**",
        _format_source_test_summary(result),
    ]
    notes = _format_source_notes(result)
    if notes is not None:
        lines.append(notes.strip())
    return "\n".join(lines)
