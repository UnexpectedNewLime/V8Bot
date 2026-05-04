"""Discord thread helpers for watch-specific delivery."""

import logging
import re
from typing import Any

import discord

from car_watch_bot.core.models import WatchDeliveryTarget

logger = logging.getLogger(__name__)
DISCORD_THREAD_NAME_LIMIT = 100


def build_watch_thread_name(target: WatchDeliveryTarget) -> str:
    """Build a compact, stable Discord thread name for a watch."""

    pieces = [_clean_name_part(target.watch_name)]
    query = _clean_name_part(target.watch_query)
    if query and query.casefold() != pieces[0].casefold():
        pieces.append(query)
    keyword_text = _keyword_text(
        target.included_keywords, existing_text=" ".join(pieces)
    )
    if keyword_text:
        pieces.append(keyword_text)
    base_name = " - ".join(part for part in pieces if part)
    raw_name = f"V8Bot: {base_name} #{target.watch_id}"
    return _truncate_thread_name(raw_name)


def build_starred_watch_thread_name(target: WatchDeliveryTarget) -> str:
    """Build the Discord thread name for a watch's starred shortlist."""

    return _truncate_thread_name(f"Starred {build_watch_thread_name(target)}")


async def resolve_watch_thread(
    client: discord.Client, target: WatchDeliveryTarget
) -> Any:
    """Return an existing or newly-created Discord thread for a watch target."""

    stored_thread = await _fetch_stored_thread(client, target.thread_id)
    if stored_thread is not None and hasattr(stored_thread, "send"):
        await _unarchive_if_needed(stored_thread, target.watch_id)
        return stored_thread

    channel = await _sendable_channel(client, target.channel_id)
    return await _create_public_thread(channel, build_watch_thread_name(target))


async def resolve_starred_watch_thread(
    client: discord.Client,
    target: WatchDeliveryTarget,
) -> Any:
    """Return an existing or newly-created Discord thread for starred listings."""

    stored_thread = await _fetch_stored_thread(client, target.starred_thread_id)
    if stored_thread is not None and hasattr(stored_thread, "send"):
        await _unarchive_if_needed(stored_thread, target.watch_id)
        return stored_thread

    channel = await _sendable_channel(client, target.channel_id)
    return await _create_public_thread(channel, build_starred_watch_thread_name(target))


async def send_to_watch_thread(
    client: discord.Client,
    target: WatchDeliveryTarget,
    **send_kwargs: Any,
) -> str:
    """Send a message to a watch thread and return the resolved thread id."""

    thread = await resolve_watch_thread(client, target)
    send_kwargs.setdefault("silent", True)
    await thread.send(**send_kwargs)
    return str(thread.id)


async def _create_public_thread(channel: Any, thread_name: str) -> Any:
    """Create a public watch thread, using fake-friendly fallbacks."""

    try:
        return await channel.create_thread(
            name=thread_name,
            type=discord.ChannelType.public_thread,
            auto_archive_duration=10080,
        )
    except TypeError:
        return await channel.create_thread(name=thread_name)


async def _fetch_stored_thread(
    client: discord.Client,
    thread_id: str | None,
) -> Any | None:
    """Fetch a stored thread id when one exists."""

    if thread_id is None:
        return None
    thread = client.get_channel(int(thread_id))
    if thread is not None:
        return thread
    try:
        return await client.fetch_channel(int(thread_id))
    except (discord.NotFound, LookupError):
        return None


async def _sendable_channel(client: discord.Client, channel_id: str) -> Any:
    """Return a Discord channel that can create threads."""

    channel = client.get_channel(int(channel_id))
    if channel is None:
        channel = await client.fetch_channel(int(channel_id))
    if not hasattr(channel, "create_thread"):
        raise RuntimeError("configured digest channel cannot create threads")
    return channel


async def _unarchive_if_needed(thread: Any, watch_id: int) -> None:
    """Unarchive a reusable thread when the bot has permission."""

    if not getattr(thread, "archived", False):
        return
    if not hasattr(thread, "edit"):
        return
    try:
        await thread.edit(archived=False)
    except discord.DiscordException:
        logger.warning(
            "failed to unarchive watch thread",
            extra={"watch_id": watch_id, "thread_id": str(thread.id)},
        )


def _keyword_text(keywords: list[str], existing_text: str) -> str:
    """Return non-redundant keywords for a thread name."""

    normalized_existing = existing_text.casefold()
    selected_keywords = [
        _clean_name_part(keyword)
        for keyword in keywords[:4]
        if _clean_name_part(keyword)
        and _clean_name_part(keyword).casefold() not in normalized_existing
    ]
    return " ".join(selected_keywords)


def _clean_name_part(value: str) -> str:
    """Normalize whitespace for a Discord thread-name component."""

    return re.sub(r"\s+", " ", value).strip()


def _truncate_thread_name(name: str) -> str:
    """Truncate a Discord thread name while preserving the watch id suffix."""

    if len(name) <= DISCORD_THREAD_NAME_LIMIT:
        return name
    prefix, separator, watch_id = name.rpartition(" #")
    suffix = f"{separator}{watch_id}" if separator else ""
    available = DISCORD_THREAD_NAME_LIMIT - len(suffix)
    if available <= 1:
        return name[:DISCORD_THREAD_NAME_LIMIT]
    return f"{prefix[:available].rstrip()}{suffix}"
