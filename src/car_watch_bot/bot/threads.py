"""Discord thread routing helpers for public bot messages."""

import logging
from collections.abc import AsyncIterator
from typing import Any

import discord


logger = logging.getLogger(__name__)
SHARED_LISTING_THREAD_NAME = "V8Bot listings"


async def resolve_shared_listing_thread(channel: Any) -> Any:
    """Return the shared listing thread for a Discord channel."""

    _ensure_sendable(channel, "configured digest channel cannot receive messages")
    thread = await _find_existing_thread(channel, SHARED_LISTING_THREAD_NAME)
    if thread is not None:
        return thread

    create_thread = getattr(channel, "create_thread", None)
    if create_thread is None:
        logger.warning(
            "discord channel cannot create listing thread; falling back to channel",
            extra={"channel_id": getattr(channel, "id", None)},
        )
        return channel

    try:
        thread = await _create_public_thread(channel, SHARED_LISTING_THREAD_NAME)
    except (discord.Forbidden, discord.HTTPException) as exc:
        logger.exception(
            "failed to create shared listing thread",
            extra={"channel_id": getattr(channel, "id", None)},
        )
        raise RuntimeError("failed to create shared listing thread") from exc

    _ensure_sendable(thread, "shared listing thread cannot receive messages")
    return thread


async def _find_existing_thread(channel: Any, thread_name: str) -> Any | None:
    """Find an active or recently archived thread with the shared name."""

    for thread in getattr(channel, "threads", []) or []:
        if _is_named_sendable_thread(thread, thread_name):
            return thread

    archived_threads = getattr(channel, "archived_threads", None)
    if archived_threads is None:
        return None

    try:
        async for thread in _iter_archived_threads(archived_threads):
            if not _is_named_sendable_thread(thread, thread_name):
                continue
            await _unarchive_thread(thread)
            return thread
    except (discord.Forbidden, discord.HTTPException):
        logger.warning(
            "failed to inspect archived listing threads",
            extra={"channel_id": getattr(channel, "id", None)},
            exc_info=True,
        )
    return None


async def _iter_archived_threads(archived_threads: Any) -> AsyncIterator[Any]:
    """Yield archived threads from discord.py or a lightweight fake."""

    try:
        thread_iterator = archived_threads(limit=50)
    except TypeError:
        thread_iterator = archived_threads()

    async for thread in thread_iterator:
        yield thread


async def _create_public_thread(channel: Any, thread_name: str) -> Any:
    """Create the shared public thread, using fake-friendly fallbacks."""

    try:
        return await channel.create_thread(
            name=thread_name,
            type=discord.ChannelType.public_thread,
            auto_archive_duration=10080,
        )
    except TypeError:
        return await channel.create_thread(name=thread_name)


async def _unarchive_thread(thread: Any) -> None:
    """Unarchive a thread when the fake or Discord object supports it."""

    edit = getattr(thread, "edit", None)
    if edit is None:
        return
    try:
        await edit(archived=False)
    except TypeError:
        await edit()


def _is_named_sendable_thread(thread: Any, thread_name: str) -> bool:
    """Return whether a thread has the target name and can receive messages."""

    return getattr(thread, "name", None) == thread_name and hasattr(thread, "send")


def _ensure_sendable(sendable: Any, error_message: str) -> None:
    """Raise when an object cannot receive Discord messages."""

    if not hasattr(sendable, "send"):
        raise RuntimeError(error_message)
