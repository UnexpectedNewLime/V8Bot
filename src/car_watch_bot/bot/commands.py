"""Discord slash command registration."""

import logging
from collections.abc import Awaitable, Callable

import discord
from discord import app_commands

from car_watch_bot.bot.embeds import build_listing_embed
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
    WatchNotFoundError,
    WatchService,
    WatchSummary,
    WatchValidationError,
)


logger = logging.getLogger(__name__)
DISCORD_MESSAGE_LIMIT = 2000
DISCORD_SAFE_MESSAGE_LIMIT = 1900


def register_commands(
    command_tree: app_commands.CommandTree[discord.Client],
    watch_service: WatchService,
    source_service: SourceService,
    listing_service: ListingService,
) -> None:
    """Register supported slash commands."""

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
        source_name: str = "AutoTempest",
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
            if not source_url.strip():
                return _format_watch_created(summary)

            source_result = await source_service.add_source_to_watch(
                discord_user_id=str(interaction.user.id),
                watch_id=summary.watch_id,
                name=source_name,
                url=source_url,
            )
            scrape_result: ScrapeNowResult | None = None
            listings: list[DigestListing] = []
            if scrape_now:
                scrape_result = await listing_service.scrape_watch_now(
                    str(interaction.user.id),
                    summary.watch_id,
                )
                listings = listing_service.list_watch_listings(
                    str(interaction.user.id),
                    summary.watch_id,
                )
                await _send_public_listing_embeds(
                    interaction,
                    summary.watch_id,
                    listings,
                    heading=f"{summary.car_query}: {len(listings)} pending listings",
                )
            return _format_watch_created_with_source(
                summary,
                source_result,
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

    @command_tree.command(name="watch_scrape_now", description="Scrape one watch now.")
    async def watch_scrape_now(interaction: discord.Interaction, watch_id: int) -> None:
        async def action() -> str:
            result = await listing_service.scrape_watch_now(
                str(interaction.user.id),
                watch_id,
            )
            listings = listing_service.list_watch_listings(str(interaction.user.id), watch_id)
            await _send_public_listing_embeds(
                interaction,
                watch_id,
                listings,
                heading=f"Watch {watch_id}: {len(listings)} pending listings",
            )
            return "\n".join(
                [
                    _format_scrape_now_result(result),
                    f"posted listing messages: {len(listings)}",
                ]
            )

        await _send_ephemeral_result(interaction, action, "failed to scrape watch")

    @command_tree.command(name="watch_listings", description="Show pending watch listings.")
    async def watch_listings(interaction: discord.Interaction, watch_id: int) -> None:
        async def action() -> str:
            listings = listing_service.list_watch_listings(str(interaction.user.id), watch_id)
            if not listings:
                return f"watch {watch_id} has no pending listings"
            await _send_public_listing_embeds(
                interaction,
                watch_id,
                listings,
                heading=f"Watch {watch_id}: {len(listings)} pending listings",
            )
            return f"posted {len(listings)} listing messages for watch {watch_id}"

        await _send_ephemeral_result(interaction, action, "failed to list watch listings")

    @command_tree.command(name="watch_remove", description="Remove one of your watches.")
    async def watch_remove(interaction: discord.Interaction, watch_id: int) -> None:
        async def action() -> str:
            watch_service.deactivate_watch(str(interaction.user.id), watch_id)
            return f"watch {watch_id} deactivated"

        await _send_ephemeral_result(interaction, action, "failed to remove watch")

    @command_tree.command(name="watch_keyword_add", description="Add a watch keyword.")
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
    async def watch_source_add(
        interaction: discord.Interaction,
        watch_id: int,
        name: str,
        url: str,
    ) -> None:
        async def action() -> str:
            result = await source_service.add_source_to_watch(
                discord_user_id=str(interaction.user.id),
                watch_id=watch_id,
                name=name,
                url=url,
            )
            return _format_source_added(result)

        await _send_ephemeral_result(interaction, action, "failed to add source")

    @command_tree.command(name="watch_source_list", description="List watch sources.")
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

    @command_tree.command(name="watch_source_test", description="Test a source URL.")
    async def watch_source_test(interaction: discord.Interaction, url: str) -> None:
        async def action() -> str:
            result = await source_service.test_source_url(str(interaction.user.id), url)
            return _format_source_test(result)

        await _send_ephemeral_result(interaction, action, "failed to test source")

    @command_tree.command(name="watch_notify_time", description="Update notify time.")
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

    await interaction.response.defer(ephemeral=True)
    try:
        message = await action()
    except (WatchValidationError, SourceValidationError) as exc:
        await _send_ephemeral_message(interaction, str(exc))
        return
    except WatchNotFoundError:
        await _send_ephemeral_message(interaction, "watch not found or not owned by you")
        return
    except SourceNotFoundError:
        await _send_ephemeral_message(interaction, "source not found for watch")
        return
    except Exception:
        logger.exception("discord command failed")
        await _send_ephemeral_message(interaction, fallback_message)
        return

    await _send_ephemeral_message(interaction, message)


async def _send_ephemeral_message(
    interaction: discord.Interaction,
    message: str,
) -> None:
    """Send a possibly long ephemeral response in Discord-safe chunks."""

    for chunk in _split_discord_message(message):
        await interaction.followup.send(chunk, ephemeral=True)


async def _send_public_listing_embeds(
    interaction: discord.Interaction,
    watch_id: int,
    listings: list[DigestListing],
    heading: str,
) -> None:
    """Send each listing as its own public channel message."""

    if not listings:
        return
    channel = interaction.channel
    if channel is None or not hasattr(channel, "send"):
        raise RuntimeError("interaction channel cannot receive messages")
    for listing in listings:
        await channel.send(
            embed=build_listing_embed(
                listing=listing,
                heading=heading,
                query=f"watch_id: {watch_id}",
            )
        )


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


def _format_watch_created(summary: WatchSummary) -> str:
    """Format watch creation confirmation."""

    return "\n".join(
        [
            f"watch ID: {summary.watch_id}",
            f"keywords: {', '.join(summary.keywords)}",
            f"notify time: {summary.notify_time}",
            f"defaults: {summary.preferred_currency}, {summary.distance_unit}",
        ]
    )


def _format_watch_created_with_source(
    summary: WatchSummary,
    source_result: SourceAddResult,
    scrape_result: ScrapeNowResult | None,
) -> str:
    """Format one-command watch setup result."""

    sections = [
        _format_watch_created(summary),
        _format_source_added(source_result),
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


def _format_watch_block(summary: WatchSummary) -> str:
    """Format one watch summary."""

    exclude_text = ", ".join(summary.exclude_keywords) or "none"
    return "\n".join(
        [
            f"watch_id: {summary.watch_id}",
            f"car query: {summary.car_query}",
            f"keywords: {', '.join(summary.keywords)}",
            f"exclude keywords: {exclude_text}",
            f"notify time: {summary.notify_time}",
            f"currency: {summary.preferred_currency}",
            f"distance unit: {summary.distance_unit}",
            f"active sources: {summary.active_sources_count}",
        ]
    )


def _format_scrape_now_result(result: ScrapeNowResult) -> str:
    """Format scrape-now result."""

    warnings = "; ".join(result.warnings) or "none"
    return "\n".join(
        [
            f"watch_id: {result.watch_id}",
            f"sources seen: {result.sources_seen}",
            f"sources scraped: {result.sources_scraped}",
            f"sources skipped: {result.sources_skipped}",
            f"new listings stored: {result.listings_created}",
            f"pending listings: {result.pending_listings}",
            f"warnings: {warnings}",
        ]
    )


def _format_watch_listings(watch_id: int, listings: list[DigestListing]) -> str:
    """Format pending listings for a watch."""

    blocks = [_format_digest_listing(listing) for listing in listings[:10]]
    if len(listings) > 10:
        blocks.append(f"...and {len(listings) - 10} more")
    return f"watch_id: {watch_id}\n" + "\n\n".join(blocks)


def _format_digest_listing(listing: DigestListing) -> str:
    """Format one pending listing."""

    reasons = ", ".join(listing.score_reasons) or "none"
    return "\n".join(
        [
            f"listing_id: {listing.listing_id}",
            f"title: {listing.title}",
            f"source: {listing.source_name}",
            f"original price: {listing.original_price}",
            f"converted price: {listing.converted_price}",
            f"original mileage: {listing.original_mileage}",
            f"converted mileage: {listing.converted_mileage}",
            f"score reasons: {reasons}",
            f"link: {listing.url}",
        ]
    )


def _format_source_added(result: SourceAddResult) -> str:
    """Format source add response."""

    return "\n".join(
        [
            "source added",
            _format_source_block(result.source),
            "source test:",
            _format_source_test(result.source_test),
        ]
    )


def _format_source_list(watch_id: int, summaries: list[SourceSummary]) -> str:
    """Format sources for a watch."""

    source_blocks = "\n\n".join(_format_source_block(summary) for summary in summaries)
    return f"watch_id: {watch_id}\n{source_blocks}"


def _format_source_block(summary: SourceSummary) -> str:
    """Format one source summary."""

    return "\n".join(
        [
            f"source_id: {summary.source_id}",
            f"name: {summary.name}",
            f"kind: {summary.kind}",
            f"url: {summary.base_url or 'none'}",
        ]
    )


def _format_source_test(result: SourceTestResult) -> str:
    """Format source test result."""

    warnings = ", ".join(result.warnings) or "none"
    errors = ", ".join(result.errors) or "none"
    return "\n".join(
        [
            f"url accepted: {result.url_accepted}",
            f"listings found: {result.listings_found}",
            f"title parsing: {result.title_parsing_worked}",
            f"link parsing: {result.link_parsing_worked}",
            f"price parsing: {result.price_parsing_worked}",
            f"mileage parsing: {result.mileage_parsing_worked}",
            f"warnings: {warnings}",
            f"errors: {errors}",
        ]
    )
