"""Tests for routing generic public Discord bot messages into shared threads."""

import asyncio
from typing import Any

from car_watch_bot.bot.threads import (
    SHARED_LISTING_THREAD_NAME,
    resolve_shared_listing_thread,
)


class FakeThread:
    """Small fake for a Discord thread-like send target."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.sent_messages: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self.edits: list[dict[str, Any]] = []

    async def send(self, *args: Any, **kwargs: Any) -> None:
        self.sent_messages.append((args, kwargs))

    async def edit(self, **kwargs: Any) -> None:
        self.edits.append(kwargs)


class FakeThreadChannel:
    """Fake Discord channel that supports creating shared threads."""

    def __init__(self) -> None:
        self.id = 123
        self.threads: list[FakeThread] = []
        self.created_threads: list[dict[str, Any]] = []
        self.sent_messages: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    async def send(self, *args: Any, **kwargs: Any) -> None:
        self.sent_messages.append((args, kwargs))

    async def create_thread(self, **kwargs: Any) -> FakeThread:
        self.created_threads.append(kwargs)
        thread = FakeThread(kwargs["name"])
        self.threads.append(thread)
        return thread


class FakePlainChannel:
    """Fake sendable channel without Discord thread support."""

    def __init__(self) -> None:
        self.id = 456
        self.sent_messages: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    async def send(self, *args: Any, **kwargs: Any) -> None:
        self.sent_messages.append((args, kwargs))


def test_shared_listing_thread_is_created_and_reused() -> None:
    channel = FakeThreadChannel()

    first_thread = asyncio.run(resolve_shared_listing_thread(channel))
    second_thread = asyncio.run(resolve_shared_listing_thread(channel))

    assert first_thread is second_thread
    assert len(channel.created_threads) == 1
    assert channel.created_threads[0]["name"] == SHARED_LISTING_THREAD_NAME
    assert channel.sent_messages == []


def test_shared_listing_thread_falls_back_when_channel_has_no_threads(
    caplog: Any,
) -> None:
    channel = FakePlainChannel()

    sendable = asyncio.run(resolve_shared_listing_thread(channel))
    asyncio.run(sendable.send("generic bot message"))

    assert sendable is channel
    assert channel.sent_messages == [(("generic bot message",), {})]
    assert "falling back to channel" in caplog.text
