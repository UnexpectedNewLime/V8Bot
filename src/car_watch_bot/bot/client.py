"""Discord client setup."""

import logging

import discord
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from discord import app_commands

from car_watch_bot.bot.commands import register_commands
from car_watch_bot.bot.embeds import build_listing_embed
from car_watch_bot.bot.watch_threads import resolve_watch_thread, send_to_watch_thread
from car_watch_bot.config import Settings
from car_watch_bot.core.models import DigestListing, DigestPayload, WatchDeliveryTarget
from car_watch_bot.services.listing_service import ListingService
from car_watch_bot.services.source_service import SourceService
from car_watch_bot.services.watch_service import WatchService


logger = logging.getLogger(__name__)


class CarWatchBotClient(discord.Client):
    """Discord client with command tree sync."""

    def __init__(
        self,
        settings: Settings,
        watch_service: WatchService,
        source_service: SourceService,
        listing_service: ListingService,
        scheduler: AsyncIOScheduler | None = None,
    ) -> None:
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.settings = settings
        self.scheduler = scheduler
        self.command_tree = app_commands.CommandTree(self)
        self._commands_synced = False
        register_commands(
            self.command_tree,
            watch_service,
            source_service,
            listing_service,
        )

    async def setup_hook(self) -> None:
        """Sync slash commands at startup."""

        if self._commands_synced:
            return
        if self.settings.discord_guild_id is not None:
            guild = discord.Object(id=self.settings.discord_guild_id)
            self.command_tree.copy_global_to(guild=guild)
            await self.command_tree.sync(guild=guild)
            logger.info("synced guild commands", extra={"guild_id": self.settings.discord_guild_id})
        else:
            await self.command_tree.sync()
            logger.info("synced global commands")
        self._commands_synced = True
        if self.scheduler is not None and not self.scheduler.running:
            self.scheduler.start()
            logger.info("started scheduler")

    async def close(self) -> None:
        """Stop scheduler before closing the Discord client."""

        if self.scheduler is not None and self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("stopped scheduler")
        await super().close()


def create_bot_client(
    settings: Settings,
    watch_service: WatchService,
    source_service: SourceService,
    listing_service: ListingService,
    scheduler: AsyncIOScheduler | None = None,
) -> CarWatchBotClient:
    """Create the Discord client."""

    return CarWatchBotClient(
        settings=settings,
        watch_service=watch_service,
        source_service=source_service,
        listing_service=listing_service,
        scheduler=scheduler,
    )


def run_bot(
    settings: Settings,
    watch_service: WatchService,
    source_service: SourceService,
    listing_service: ListingService,
    scheduler: AsyncIOScheduler | None = None,
) -> None:
    """Run the Discord bot."""

    if not settings.discord_bot_token:
        raise RuntimeError("DISCORD_BOT_TOKEN is required to run the bot")
    client = create_bot_client(
        settings,
        watch_service,
        source_service,
        listing_service,
        scheduler,
    )
    client.run(settings.discord_bot_token)


class DiscordDigestSender:
    """Send digest payloads to Discord channels as embeds."""

    def __init__(self, client: discord.Client) -> None:
        self.client = client

    async def send_digest(
        self,
        target: WatchDeliveryTarget,
        digest: DigestPayload,
    ) -> str | None:
        """Send one digest payload to a watch thread."""

        thread = await resolve_watch_thread(self.client, target)
        for embed in _build_digest_embeds(digest):
            await thread.send(embed=embed, silent=True)
        return str(thread.id)

    async def send_no_updates(self, target: WatchDeliveryTarget) -> str | None:
        """Send a no-update digest confirmation to a watch thread."""

        return await send_to_watch_thread(
            self.client,
            target,
            content=f"{target.watch_name}: scheduled check complete, no new listings.",
        )


def _build_digest_embeds(digest: DigestPayload) -> list[discord.Embed]:
    """Build Discord embeds for a digest payload."""

    return [
        build_listing_embed(
            listing=listing,
            heading=f"{digest.watch_name}: {digest.listing_count} new listings",
            query=digest.watch_query,
        )
        for listing in digest.listings
    ]


def _format_listing_embed_value(listing: DigestListing) -> str:
    """Format one digest listing as an embed field value."""

    reasons = ", ".join(listing.score_reasons) or "none"
    return "\n".join(
        [
            f"Source: {listing.source_name}",
            f"Original price: {listing.original_price}",
            f"Converted price: {listing.converted_price}",
            f"Original mileage: {listing.original_mileage}",
            f"Converted mileage: {listing.converted_mileage}",
            f"Score reasons: {reasons}",
            f"Link: {listing.url}",
        ]
    )[:1024]
