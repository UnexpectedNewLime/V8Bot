"""Discord listing action buttons."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import discord

from car_watch_bot.bot.watch_threads import resolve_starred_watch_thread
from car_watch_bot.core.listing_status import (
    LISTING_STATUS_INACTIVE,
    LISTING_STATUS_SENT,
    LISTING_STATUS_STARRED,
)
from car_watch_bot.services.listing_service import (
    ListingService,
    ListingStatusValidationError,
    WatchListingNotFoundError,
)
from car_watch_bot.services.watch_service import (
    WatchNotFoundError,
    WatchService,
    WatchValidationError,
)

logger = logging.getLogger(__name__)

LISTING_ACTION_CUSTOM_ID_PREFIX = "v8bot:listing-action"
LISTING_ACTION_NAMES = ("star", "delete")
STARRED_LISTING_ACTION_NAMES = ("unstar",)
ALL_LISTING_ACTION_NAMES = (*LISTING_ACTION_NAMES, *STARRED_LISTING_ACTION_NAMES)
LISTING_ACTION_CUSTOM_ID_PATTERN = re.compile(
    rf"^{LISTING_ACTION_CUSTOM_ID_PREFIX}:"
    rf"(?P<action>{'|'.join(ALL_LISTING_ACTION_NAMES)}):"
    r"(?P<watch_id>[0-9]+):(?P<listing_id>[0-9]+)$"
)


@dataclass(frozen=True)
class ListingActionSpec:
    """Discord presentation details for one listing action."""

    label: str
    status: str
    style: discord.ButtonStyle
    confirmation: str


@dataclass(frozen=True)
class ListingActionCustomId:
    """Parsed listing-action custom id."""

    action: str
    watch_id: int
    listing_id: int


LISTING_ACTION_SPECS: dict[str, ListingActionSpec] = {
    "star": ListingActionSpec(
        label="Star",
        status=LISTING_STATUS_STARRED,
        style=discord.ButtonStyle.success,
        confirmation="starred",
    ),
    "delete": ListingActionSpec(
        label="Delete",
        status=LISTING_STATUS_INACTIVE,
        style=discord.ButtonStyle.danger,
        confirmation="deleted",
    ),
    "unstar": ListingActionSpec(
        label="Unstar",
        status=LISTING_STATUS_SENT,
        style=discord.ButtonStyle.secondary,
        confirmation="unstarred",
    ),
}


class ListingActionView(discord.ui.View):
    """Persistent view containing listing action buttons."""

    def __init__(self, watch_id: int, listing_id: int) -> None:
        super().__init__(timeout=None)
        for action in LISTING_ACTION_NAMES:
            self.add_item(ListingActionDynamicItem(action, watch_id, listing_id))


class StarredListingActionView(discord.ui.View):
    """Persistent view containing starred-listing action buttons."""

    def __init__(self, watch_id: int, listing_id: int) -> None:
        super().__init__(timeout=None)
        for action in STARRED_LISTING_ACTION_NAMES:
            self.add_item(ListingActionDynamicItem(action, watch_id, listing_id))


class ListingActionDynamicItem(
    discord.ui.DynamicItem[discord.ui.Button],
    template=LISTING_ACTION_CUSTOM_ID_PATTERN,
):
    """Dynamic persistent listing action button."""

    def __init__(self, action: str, watch_id: int, listing_id: int) -> None:
        spec = LISTING_ACTION_SPECS[action]
        super().__init__(
            discord.ui.Button(
                label=spec.label,
                style=spec.style,
                custom_id=build_listing_action_custom_id(action, watch_id, listing_id),
            )
        )
        self.action = action
        self.watch_id = watch_id
        self.listing_id = listing_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match: re.Match[str],
    ) -> ListingActionDynamicItem:
        """Rebuild a dynamic button from its custom id."""

        parsed = ListingActionCustomId(
            action=match.group("action"),
            watch_id=int(match.group("watch_id")),
            listing_id=int(match.group("listing_id")),
        )
        return cls(parsed.action, parsed.watch_id, parsed.listing_id)

    async def callback(self, interaction: discord.Interaction) -> None:
        """Apply the clicked listing action."""

        await handle_listing_action_interaction(
            interaction=interaction,
            action=self.action,
            watch_id=self.watch_id,
            listing_id=self.listing_id,
        )


class DeleteListingConfirmationModal(discord.ui.Modal):
    """Modal confirmation for deleting one listing message."""

    def __init__(
        self,
        watch_id: int,
        listing_id: int,
        listing_message: discord.Message | None,
    ) -> None:
        super().__init__(title=f"Delete listing {listing_id}")
        self.watch_id = watch_id
        self.listing_id = listing_id
        self.listing_message = listing_message
        self.delete_reason = discord.ui.TextInput(
            label="Delete reason (optional)",
            placeholder="Submit confirms. Cancel keeps the listing.",
            required=False,
            max_length=240,
        )
        self.add_item(self.delete_reason)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Confirm deletion of the listing row and Discord message."""

        await handle_delete_listing_confirmation(
            interaction=interaction,
            watch_id=self.watch_id,
            listing_id=self.listing_id,
            listing_message=self.listing_message,
            delete_reason=self.delete_reason_value,
        )

    @property
    def delete_reason_value(self) -> str | None:
        """Return the optional user-provided delete reason."""

        reason = self.delete_reason.value.strip()
        return reason or None


class UnstarListingConfirmationModal(discord.ui.Modal):
    """Modal confirmation for removing one starred-listing message."""

    def __init__(
        self,
        watch_id: int,
        listing_id: int,
        starred_message: discord.Message | None,
    ) -> None:
        super().__init__(title=f"Unstar listing {listing_id}")
        self.watch_id = watch_id
        self.listing_id = listing_id
        self.starred_message = starred_message
        self.note = discord.ui.TextInput(
            label="Confirm unstar",
            placeholder="Submit confirms. Cancel keeps the starred copy.",
            required=False,
            max_length=100,
        )
        self.add_item(self.note)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Confirm removal of the starred copy."""

        await handle_unstar_listing_confirmation(
            interaction=interaction,
            watch_id=self.watch_id,
            listing_id=self.listing_id,
            starred_message=self.starred_message,
        )


def build_listing_action_view(watch_id: int, listing_id: int) -> ListingActionView:
    """Build a persistent action view for one watch listing."""

    return ListingActionView(watch_id=watch_id, listing_id=listing_id)


def build_starred_listing_action_view(
    watch_id: int,
    listing_id: int,
) -> StarredListingActionView:
    """Build a persistent action view for one starred watch listing."""

    return StarredListingActionView(watch_id=watch_id, listing_id=listing_id)


def build_listing_action_custom_id(action: str, watch_id: int, listing_id: int) -> str:
    """Build the stable Discord custom id for a listing action."""

    if action not in LISTING_ACTION_SPECS:
        raise ValueError("unsupported listing action")
    return f"{LISTING_ACTION_CUSTOM_ID_PREFIX}:{action}:{watch_id}:{listing_id}"


def parse_listing_action_custom_id(custom_id: str) -> ListingActionCustomId | None:
    """Parse a listing action custom id."""

    match = LISTING_ACTION_CUSTOM_ID_PATTERN.fullmatch(custom_id)
    if match is None:
        return None
    return ListingActionCustomId(
        action=match.group("action"),
        watch_id=int(match.group("watch_id")),
        listing_id=int(match.group("listing_id")),
    )


async def handle_listing_action_interaction(
    *,
    interaction: discord.Interaction,
    action: str,
    watch_id: int,
    listing_id: int,
) -> None:
    """Handle a Discord listing action interaction."""

    if action == "delete":
        await _send_delete_confirmation(
            interaction=interaction,
            watch_id=watch_id,
            listing_id=listing_id,
        )
        return
    if action == "unstar":
        await _send_unstar_confirmation(
            interaction=interaction,
            watch_id=watch_id,
            listing_id=listing_id,
        )
        return
    if action != "star":
        await _send_ephemeral_response(interaction, "listing action is not supported")
        return

    await _handle_star_listing_interaction(
        interaction=interaction,
        watch_id=watch_id,
        listing_id=listing_id,
    )


async def handle_delete_listing_confirmation(
    *,
    interaction: discord.Interaction,
    watch_id: int,
    listing_id: int,
    listing_message: discord.Message | None,
    delete_reason: str | None = None,
) -> None:
    """Apply a confirmed listing delete action."""

    listing_service = _listing_service_from_interaction(interaction)
    if listing_service is None:
        logger.error("listing delete missing listing service")
        await _send_ephemeral_response(
            interaction,
            "listing actions are unavailable",
        )
        return

    try:
        listing_service.update_watch_listing_status(
            discord_user_id=str(interaction.user.id),
            watch_id=watch_id,
            listing_id=listing_id,
            status=LISTING_STATUS_INACTIVE,
        )
    except (WatchNotFoundError, WatchListingNotFoundError):
        logger.info(
            "listing delete rejected user_id=%s watch_id=%s listing_id=%s",
            interaction.user.id,
            watch_id,
            listing_id,
        )
        await _send_ephemeral_response(
            interaction,
            "listing not found or not owned by you",
        )
        return
    except ListingStatusValidationError:
        logger.info("listing delete validation failed")
        await _send_ephemeral_response(
            interaction,
            "listing action is not supported",
        )
        return
    except Exception:
        logger.exception(
            "listing delete failed user_id=%s watch_id=%s listing_id=%s",
            interaction.user.id,
            watch_id,
            listing_id,
        )
        await _send_ephemeral_response(
            interaction,
            "failed to delete listing",
        )
        return

    message_deleted = await _delete_listing_message(
        listing_message=listing_message,
        watch_id=watch_id,
        listing_id=listing_id,
    )
    if message_deleted:
        confirmation = f"Listing {listing_id} deleted."
    else:
        confirmation = (
            f"Listing {listing_id} deleted, but I could not remove the Discord message."
        )
    logger.info(
        "listing delete applied user_id=%s watch_id=%s listing_id=%s message_deleted=%s",
        interaction.user.id,
        watch_id,
        listing_id,
        message_deleted,
        extra={"delete_reason": delete_reason},
    )
    await _send_ephemeral_response(interaction, confirmation)


async def handle_unstar_listing_confirmation(
    *,
    interaction: discord.Interaction,
    watch_id: int,
    listing_id: int,
    starred_message: discord.Message | None,
) -> None:
    """Apply a confirmed starred-listing removal."""

    listing_service = _listing_service_from_interaction(interaction)
    if listing_service is None:
        logger.error("listing unstar missing listing service")
        await _send_ephemeral_response(interaction, "listing actions are unavailable")
        return

    try:
        listing_service.unstar_watch_listing(
            discord_user_id=str(interaction.user.id),
            watch_id=watch_id,
            listing_id=listing_id,
        )
    except (WatchNotFoundError, WatchListingNotFoundError):
        logger.info(
            "listing unstar rejected user_id=%s watch_id=%s listing_id=%s",
            interaction.user.id,
            watch_id,
            listing_id,
        )
        await _send_ephemeral_response(
            interaction,
            "listing not found or not owned by you",
        )
        return
    except Exception:
        logger.exception(
            "listing unstar failed user_id=%s watch_id=%s listing_id=%s",
            interaction.user.id,
            watch_id,
            listing_id,
        )
        await _send_ephemeral_response(interaction, "failed to unstar listing")
        return

    message_deleted = await _delete_listing_message(
        listing_message=starred_message,
        watch_id=watch_id,
        listing_id=listing_id,
    )
    if message_deleted:
        confirmation = f"Listing {listing_id} unstarred."
    else:
        confirmation = f"Listing {listing_id} unstarred, but I could not remove the starred message."
    logger.info(
        "listing unstar applied user_id=%s watch_id=%s listing_id=%s message_deleted=%s",
        interaction.user.id,
        watch_id,
        listing_id,
        message_deleted,
    )
    await _send_ephemeral_response(interaction, confirmation)


async def _handle_star_listing_interaction(
    *,
    interaction: discord.Interaction,
    watch_id: int,
    listing_id: int,
) -> None:
    """Star one listing and copy it into the watch's starred thread."""

    action = "star"
    spec = LISTING_ACTION_SPECS[action]
    listing_service = _listing_service_from_interaction(interaction)
    watch_service = _watch_service_from_interaction(interaction)
    if listing_service is None or watch_service is None:
        logger.error("listing action missing listing service")
        await _send_ephemeral_response(interaction, "listing actions are unavailable")
        return

    try:
        listing_service.update_watch_listing_status(
            discord_user_id=str(interaction.user.id),
            watch_id=watch_id,
            listing_id=listing_id,
            status=spec.status,
        )
        target = watch_service.get_delivery_target(
            discord_user_id=str(interaction.user.id),
            watch_id=watch_id,
        )
        starred_thread = await resolve_starred_watch_thread(interaction.client, target)
        await _send_starred_listing_message(
            starred_thread=starred_thread,
            interaction=interaction,
            watch_id=watch_id,
            listing_id=listing_id,
        )
        starred_thread_id = str(starred_thread.id)
        if starred_thread_id != target.starred_thread_id:
            watch_service.set_starred_thread_id(
                str(interaction.user.id),
                watch_id,
                starred_thread_id,
            )
    except (WatchNotFoundError, WatchListingNotFoundError):
        logger.info(
            "listing action rejected user_id=%s watch_id=%s listing_id=%s action=%s",
            interaction.user.id,
            watch_id,
            listing_id,
            action,
        )
        await _send_ephemeral_response(
            interaction,
            "listing not found or not owned by you",
        )
        return
    except WatchValidationError as exc:
        logger.info(
            "listing star validation failed user_id=%s watch_id=%s error=%s",
            interaction.user.id,
            watch_id,
            exc,
        )
        await _send_ephemeral_response(interaction, str(exc))
        return
    except ListingStatusValidationError:
        logger.info("listing action validation failed action=%s", action)
        await _send_ephemeral_response(interaction, "listing action is not supported")
        return
    except Exception:
        logger.exception(
            "listing action failed user_id=%s watch_id=%s listing_id=%s action=%s",
            interaction.user.id,
            watch_id,
            listing_id,
            action,
        )
        await _send_ephemeral_response(interaction, "failed to update listing")
        return

    logger.info(
        (
            "listing action applied user_id=%s watch_id=%s listing_id=%s "
            "action=%s status=%s"
        ),
        interaction.user.id,
        watch_id,
        listing_id,
        action,
        spec.status,
    )
    await _send_ephemeral_response(
        interaction,
        f"Listing {listing_id} {spec.confirmation}.",
    )


async def _send_delete_confirmation(
    *,
    interaction: discord.Interaction,
    watch_id: int,
    listing_id: int,
) -> None:
    """Ask the user to confirm a destructive listing action."""

    await interaction.response.send_modal(
        DeleteListingConfirmationModal(
            watch_id=watch_id,
            listing_id=listing_id,
            listing_message=getattr(interaction, "message", None),
        ),
    )


async def _send_unstar_confirmation(
    *,
    interaction: discord.Interaction,
    watch_id: int,
    listing_id: int,
) -> None:
    """Ask the user to confirm removal from the starred shortlist."""

    await interaction.response.send_modal(
        UnstarListingConfirmationModal(
            watch_id=watch_id,
            listing_id=listing_id,
            starred_message=getattr(interaction, "message", None),
        ),
    )


async def _send_starred_listing_message(
    *,
    starred_thread: discord.abc.Messageable,
    interaction: discord.Interaction,
    watch_id: int,
    listing_id: int,
) -> None:
    """Copy the clicked listing message into the starred shortlist thread."""

    send_kwargs: dict[str, object] = {
        "view": build_starred_listing_action_view(watch_id, listing_id),
        "silent": True,
    }
    source_message = getattr(interaction, "message", None)
    source_embeds = getattr(source_message, "embeds", None) or []
    if source_embeds:
        source_embed = source_embeds[0]
        copy_embed = getattr(source_embed, "copy", None)
        send_kwargs["embed"] = copy_embed() if copy_embed is not None else source_embed
    else:
        send_kwargs["content"] = f"Starred listing {listing_id}."
    await starred_thread.send(**send_kwargs)


async def _delete_listing_message(
    *,
    listing_message: discord.Message | None,
    watch_id: int,
    listing_id: int,
) -> bool:
    """Delete the public listing message when possible."""

    delete = getattr(listing_message, "delete", None)
    if delete is None:
        return False
    try:
        await delete()
    except (discord.NotFound, discord.Forbidden):
        logger.info(
            "listing message already gone or not deletable watch_id=%s listing_id=%s",
            watch_id,
            listing_id,
        )
        return False
    except Exception:
        logger.exception(
            "failed to delete listing message watch_id=%s listing_id=%s",
            watch_id,
            listing_id,
        )
        return False
    return True


def _listing_service_from_interaction(
    interaction: discord.Interaction,
) -> ListingService | None:
    """Return the listing service attached to a Discord client."""

    listing_service = getattr(interaction.client, "listing_service", None)
    if not isinstance(listing_service, ListingService):
        return None
    return listing_service


def _watch_service_from_interaction(
    interaction: discord.Interaction,
) -> WatchService | None:
    """Return the watch service attached to a Discord client."""

    watch_service = getattr(interaction.client, "watch_service", None)
    if not isinstance(watch_service, WatchService):
        return None
    return watch_service


async def _send_ephemeral_response(
    interaction: discord.Interaction,
    message: str,
    view: discord.ui.View | None = None,
) -> None:
    """Send one ephemeral response for a component interaction."""

    response_kwargs: dict[str, object] = {"ephemeral": True}
    if view is not None:
        response_kwargs["view"] = view

    if interaction.response.is_done():
        await interaction.followup.send(message, **response_kwargs)
        return
    await interaction.response.send_message(message, **response_kwargs)
