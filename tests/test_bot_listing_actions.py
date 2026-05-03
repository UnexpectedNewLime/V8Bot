"""Tests for Discord listing action buttons."""

import asyncio

import pytest

from car_watch_bot.bot.listing_actions import (
    DeleteListingConfirmationModal,
    LISTING_ACTION_NAMES,
    STARRED_LISTING_ACTION_NAMES,
    UnstarListingConfirmationModal,
    build_listing_action_custom_id,
    build_listing_action_view,
    build_starred_listing_action_view,
    handle_delete_listing_confirmation,
    handle_listing_action_interaction,
    handle_unstar_listing_confirmation,
    parse_listing_action_custom_id,
)
from car_watch_bot.core.listing_status import (
    LISTING_STATUS_INACTIVE,
    LISTING_STATUS_SENT,
    LISTING_STATUS_STARRED,
)
from car_watch_bot.core.models import WatchDeliveryTarget
from car_watch_bot.services.listing_service import ListingService
from car_watch_bot.services.watch_service import WatchService


def test_listing_action_custom_id_round_trips() -> None:
    custom_id = build_listing_action_custom_id("unstar", 42, 7)

    parsed = parse_listing_action_custom_id(custom_id)

    assert parsed is not None
    assert parsed.action == "unstar"
    assert parsed.watch_id == 42
    assert parsed.listing_id == 7


def test_listing_action_custom_id_rejects_unknown_action() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        build_listing_action_custom_id("archive", 42, 7)

    assert parse_listing_action_custom_id("v8bot:listing-action:archive:42:7") is None
    assert parse_listing_action_custom_id("not-a-v8bot-action") is None


def test_listing_action_view_contains_persistent_buttons() -> None:
    view = build_listing_action_view(watch_id=42, listing_id=7)

    custom_ids = [child.custom_id for child in view.children]
    labels = [child.item.label for child in view.children]

    assert view.timeout is None
    assert view.is_persistent()
    assert custom_ids == [
        build_listing_action_custom_id(action, 42, 7) for action in LISTING_ACTION_NAMES
    ]
    assert labels == ["Star", "Delete"]


def test_starred_listing_action_view_contains_only_unstar() -> None:
    view = build_starred_listing_action_view(watch_id=42, listing_id=7)

    custom_ids = [child.custom_id for child in view.children]
    labels = [child.item.label for child in view.children]

    assert view.timeout is None
    assert view.is_persistent()
    assert custom_ids == [
        build_listing_action_custom_id(action, 42, 7)
        for action in STARRED_LISTING_ACTION_NAMES
    ]
    assert labels == ["Unstar"]


def test_star_action_calls_listing_service_and_posts_to_starred_thread() -> None:
    listing_service = FakeListingService()
    watch_service = FakeWatchService()
    channel = FakeChannel()
    interaction = FakeInteraction(
        listing_service=listing_service,
        watch_service=watch_service,
        channels={999: channel},
        message=FakeListingMessage(embeds=[FakeEmbed("listing embed")]),
    )

    asyncio.run(
        handle_listing_action_interaction(
            interaction=interaction,
            action="star",
            watch_id=42,
            listing_id=7,
        )
    )

    assert listing_service.calls == [("123", 42, 7, LISTING_STATUS_STARRED)]
    assert len(channel.created_threads) == 1
    assert channel.thread_kwargs[0]["name"] == "Starred V8Bot: C5 Corvette - manual #42"
    assert (
        channel.created_threads[0].sent_messages[0]["embed"].name
        == "listing embed copy"
    )
    assert channel.created_threads[0].sent_messages[0]["view"].is_persistent()
    assert [
        child.item.label
        for child in channel.created_threads[0].sent_messages[0]["view"].children
    ] == [
        "Unstar",
    ]
    assert watch_service.starred_thread_updates == [("123", 42, "900")]
    assert interaction.response.sent_messages == [
        ("Listing 7 starred.", True, None),
    ]


def test_delete_action_opens_confirmation_modal() -> None:
    listing_service = FakeListingService()
    interaction = FakeInteraction(
        listing_service=listing_service,
        watch_service=FakeWatchService(),
        channels={999: FakeChannel()},
        message=FakeListingMessage(),
    )

    asyncio.run(
        handle_listing_action_interaction(
            interaction=interaction,
            action="delete",
            watch_id=42,
            listing_id=7,
        )
    )

    assert listing_service.calls == []
    assert isinstance(interaction.response.modals[0], DeleteListingConfirmationModal)
    assert interaction.response.modals[0].listing_message is interaction.message
    assert interaction.response.modals[0].delete_reason.required is False


def test_delete_confirmation_modal_builds_optional_reason() -> None:
    modal = DeleteListingConfirmationModal(
        watch_id=42,
        listing_id=7,
        listing_message=FakeListingMessage(),
    )

    assert modal.delete_reason_value is None

    modal.delete_reason._value = "Price too high"
    assert modal.delete_reason_value == "Price too high"


def test_delete_confirmation_inactivates_listing_and_deletes_message() -> None:
    listing_service = FakeListingService()
    listing_message = FakeListingMessage()
    interaction = FakeInteraction(
        listing_service=listing_service,
        watch_service=FakeWatchService(),
        channels={999: FakeChannel()},
    )

    asyncio.run(
        handle_delete_listing_confirmation(
            interaction=interaction,
            watch_id=42,
            listing_id=7,
            listing_message=listing_message,
        )
    )

    assert listing_service.calls == [("123", 42, 7, LISTING_STATUS_INACTIVE)]
    assert listing_message.deleted is True
    assert interaction.response.sent_messages == [("Listing 7 deleted.", True, None)]


def test_unstar_action_opens_confirmation_modal() -> None:
    interaction = FakeInteraction(
        listing_service=FakeListingService(),
        watch_service=FakeWatchService(),
        channels={999: FakeChannel()},
        message=FakeListingMessage(),
    )

    asyncio.run(
        handle_listing_action_interaction(
            interaction=interaction,
            action="unstar",
            watch_id=42,
            listing_id=7,
        )
    )

    assert isinstance(interaction.response.modals[0], UnstarListingConfirmationModal)
    assert interaction.response.modals[0].starred_message is interaction.message
    assert interaction.response.modals[0].note.required is False


def test_unstar_confirmation_marks_sent_and_deletes_starred_message() -> None:
    listing_service = FakeListingService()
    starred_message = FakeListingMessage()
    interaction = FakeInteraction(
        listing_service=listing_service,
        watch_service=FakeWatchService(),
        channels={999: FakeChannel()},
    )

    asyncio.run(
        handle_unstar_listing_confirmation(
            interaction=interaction,
            watch_id=42,
            listing_id=7,
            starred_message=starred_message,
        )
    )

    assert listing_service.unstar_calls == [("123", 42, 7)]
    assert listing_service.calls == []
    assert starred_message.deleted is True
    assert interaction.response.sent_messages == [("Listing 7 unstarred.", True, None)]


class FakeListingService(ListingService):
    """Listing service test double."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int, int, str]] = []
        self.unstar_calls: list[tuple[str, int, int]] = []

    def update_watch_listing_status(
        self,
        discord_user_id: str,
        watch_id: int,
        listing_id: int,
        status: str,
    ) -> object:
        """Record a status update."""

        self.calls.append((discord_user_id, watch_id, listing_id, status))
        return object()

    def unstar_watch_listing(
        self,
        discord_user_id: str,
        watch_id: int,
        listing_id: int,
    ) -> object:
        """Record an unstar update."""

        self.unstar_calls.append((discord_user_id, watch_id, listing_id))
        return object()


class FakeWatchService(WatchService):
    """Watch service test double."""

    def __init__(self) -> None:
        self.starred_thread_updates: list[tuple[str, int, str | None]] = []

    def get_delivery_target(
        self,
        discord_user_id: str,
        watch_id: int,
    ) -> WatchDeliveryTarget:
        """Return a fake watch delivery target."""

        return WatchDeliveryTarget(
            watch_id=watch_id,
            watch_name="C5 Corvette",
            watch_query="C5 Corvette",
            included_keywords=["manual"],
            channel_id="999",
            thread_id=None,
            starred_thread_id=None,
        )

    def set_starred_thread_id(
        self,
        discord_user_id: str,
        watch_id: int,
        thread_id: str | None,
    ) -> WatchDeliveryTarget:
        """Record starred thread persistence."""

        self.starred_thread_updates.append((discord_user_id, watch_id, thread_id))
        return self.get_delivery_target(discord_user_id, watch_id)


class FakeInteraction:
    """Discord interaction test double."""

    def __init__(
        self,
        listing_service: FakeListingService,
        watch_service: FakeWatchService,
        channels: dict[int, object],
        message: object | None = None,
    ) -> None:
        self.client = FakeClient(listing_service, watch_service, channels)
        self.user = FakeUser()
        self.response = FakeResponse()
        self.followup = FakeFollowup()
        self.message = message


class FakeClient:
    """Discord client test double."""

    def __init__(
        self,
        listing_service: FakeListingService,
        watch_service: FakeWatchService,
        channels: dict[int, object],
    ) -> None:
        self.listing_service = listing_service
        self.watch_service = watch_service
        self.channels = channels

    def get_channel(self, channel_id: int) -> object | None:
        """Return a fake cached channel."""

        return self.channels.get(channel_id)

    async def fetch_channel(self, channel_id: int) -> object:
        """Return a fake fetched channel."""

        return self.channels[channel_id]


class FakeChannel:
    """Discord channel test double."""

    def __init__(self) -> None:
        self.created_threads: list[FakeThread] = []
        self.thread_kwargs: list[dict[str, object]] = []

    async def create_thread(self, **kwargs: object) -> object:
        """Create a fake public thread."""

        self.thread_kwargs.append(kwargs)
        thread = FakeThread(900 + len(self.created_threads))
        self.created_threads.append(thread)
        return thread


class FakeThread:
    """Discord thread test double."""

    def __init__(self, thread_id: int) -> None:
        self.id = thread_id
        self.sent_messages: list[dict[str, object]] = []

    async def send(self, **kwargs: object) -> None:
        """Record a thread send."""

        self.sent_messages.append(kwargs)


class FakeListingMessage:
    """Discord listing message test double."""

    def __init__(self, embeds: list[object] | None = None) -> None:
        self.embeds = embeds or []
        self.deleted = False

    async def delete(self) -> None:
        """Record message deletion."""

        self.deleted = True


class FakeEmbed:
    """Discord embed test double."""

    def __init__(self, name: str) -> None:
        self.name = name

    def copy(self) -> "FakeEmbed":
        """Return a copied fake embed."""

        return FakeEmbed(f"{self.name} copy")


class FakeUser:
    """Discord user test double."""

    id = 123


_MISSING = object()


class FakeResponse:
    """Discord response test double."""

    def __init__(self) -> None:
        self.sent_messages: list[tuple[str, bool, object | None]] = []
        self.edited_messages: list[tuple[str, object | None]] = []
        self.modals: list[object] = []

    def is_done(self) -> bool:
        """Return whether an initial response has already been sent."""

        return bool(self.sent_messages or self.edited_messages)

    async def send_message(
        self,
        message: str,
        ephemeral: bool,
        view: object = _MISSING,
    ) -> None:
        """Record a response message."""

        if view is None:
            raise AttributeError("'NoneType' object has no attribute 'is_finished'")
        view_value = None if view is _MISSING else view
        self.sent_messages.append((message, ephemeral, view_value))

    async def edit_message(self, content: str, view: object | None = None) -> None:
        """Record an edited response message."""

        self.edited_messages.append((content, view))

    async def send_modal(self, modal: object) -> None:
        """Record a sent modal."""

        self.modals.append(modal)


class FakeFollowup:
    """Discord followup test double."""

    def __init__(self) -> None:
        self.sent_messages: list[tuple[str, bool, object | None]] = []

    async def send(
        self,
        message: str,
        ephemeral: bool,
        view: object = _MISSING,
    ) -> None:
        """Record a followup message."""

        if view is None:
            raise AttributeError("'NoneType' object has no attribute 'is_finished'")
        view_value = None if view is _MISSING else view
        self.sent_messages.append((message, ephemeral, view_value))
