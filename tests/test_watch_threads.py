"""Tests for watch-specific Discord thread helpers."""

import asyncio

from car_watch_bot.bot.client import DiscordDigestSender
from car_watch_bot.bot.watch_threads import (
    DISCORD_THREAD_NAME_LIMIT,
    build_watch_thread_name,
    resolve_watch_thread,
)
from car_watch_bot.core.models import DigestListing, DigestPayload, WatchDeliveryTarget


class FakeThread:
    """Minimal Discord thread test double."""

    def __init__(self, thread_id: int, archived: bool = False) -> None:
        self.id = thread_id
        self.archived = archived
        self.sent_messages: list[dict[str, object]] = []
        self.edit_calls: list[dict[str, object]] = []

    async def send(self, **kwargs: object) -> None:
        """Record a sent message."""

        self.sent_messages.append(kwargs)

    async def edit(self, **kwargs: object) -> None:
        """Record an edit and apply archive state."""

        self.edit_calls.append(kwargs)
        if "archived" in kwargs:
            self.archived = bool(kwargs["archived"])


class FakeChannel:
    """Minimal Discord text channel test double."""

    def __init__(self) -> None:
        self.created_threads: list[FakeThread] = []
        self.thread_kwargs: list[dict[str, object]] = []

    async def create_thread(self, **kwargs: object) -> FakeThread:
        """Create a fake thread."""

        thread = FakeThread(900 + len(self.created_threads))
        self.created_threads.append(thread)
        self.thread_kwargs.append(kwargs)
        return thread


class FakeClient:
    """Minimal Discord client test double."""

    def __init__(self) -> None:
        self.channels: dict[int, object] = {}
        self.fetch_missing_ids: set[int] = set()

    def get_channel(self, channel_id: int) -> object | None:
        """Return a cached channel or thread."""

        return self.channels.get(channel_id)

    async def fetch_channel(self, channel_id: int) -> object:
        """Fetch a channel or simulate a deleted thread."""

        if channel_id in self.fetch_missing_ids:
            raise LookupError("missing channel")
        return self.channels[channel_id]


def _target(thread_id: str | None = None) -> WatchDeliveryTarget:
    return WatchDeliveryTarget(
        watch_id=42,
        watch_name="C5 Corvette",
        watch_query="C5 Corvette",
        included_keywords=["manual", "targa", "C5"],
        channel_id="123",
        thread_id=thread_id,
    )


def test_build_watch_thread_name_is_meaningful_and_stable() -> None:
    name = build_watch_thread_name(_target())

    assert name == "V8Bot: C5 Corvette - manual targa #42"


def test_build_watch_thread_name_truncates_long_inputs() -> None:
    target = WatchDeliveryTarget(
        watch_id=12345,
        watch_name="Very long Chevrolet Corvette name " * 5,
        watch_query="C5 Corvette Z06 manual targa collector edition",
        included_keywords=["manual", "targa", "heads up display"],
        channel_id="123",
        thread_id=None,
    )

    name = build_watch_thread_name(target)

    assert len(name) <= DISCORD_THREAD_NAME_LIMIT
    assert name.endswith("#12345")


def test_resolve_watch_thread_reuses_and_unarchives_stored_thread() -> None:
    client = FakeClient()
    stored_thread = FakeThread(555, archived=True)
    client.channels[555] = stored_thread

    resolved_thread = asyncio.run(resolve_watch_thread(client, _target(thread_id="555")))

    assert resolved_thread is stored_thread
    assert stored_thread.archived is False
    assert stored_thread.edit_calls == [{"archived": False}]


def test_resolve_watch_thread_recovers_deleted_thread_with_replacement() -> None:
    client = FakeClient()
    channel = FakeChannel()
    client.channels[123] = channel
    client.fetch_missing_ids.add(555)

    resolved_thread = asyncio.run(resolve_watch_thread(client, _target(thread_id="555")))

    assert resolved_thread is channel.created_threads[0]
    assert channel.thread_kwargs[0]["name"] == "V8Bot: C5 Corvette - manual targa #42"
    assert channel.thread_kwargs[0]["type"].name == "public_thread"


def test_discord_digest_sender_reuses_created_thread_for_each_embed() -> None:
    client = FakeClient()
    channel = FakeChannel()
    client.channels[123] = channel
    sender = DiscordDigestSender(client)
    digest = DigestPayload(
        watch_name="C5 Corvette",
        watch_query="C5 Corvette",
        listing_count=2,
        listings=[
            _listing(1),
            _listing(2),
        ],
    )

    thread_id = asyncio.run(sender.send_digest(_target(), digest))

    assert thread_id == "900"
    assert len(channel.created_threads) == 1
    assert len(channel.created_threads[0].sent_messages) == 2
    assert channel.created_threads[0].sent_messages[0]["silent"] is True


def _listing(listing_id: int) -> DigestListing:
    return DigestListing(
        listing_id=listing_id,
        title=f"C5 Corvette {listing_id}",
        source_name="Mock Cars",
        original_price="USD 10,000",
        converted_price="AUD 15,000",
        original_mileage="10,000 mi",
        converted_mileage="16,093 km",
        score_reasons=["keyword matched: manual"],
        url=f"https://example.test/{listing_id}",
    )
