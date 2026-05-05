"""Notification service for scheduled digests."""

import logging
from datetime import datetime, time, timezone
from typing import Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session, sessionmaker

from car_watch_bot.core.models import DigestPayload, WatchDeliveryTarget
from car_watch_bot.db.models import Watch
from car_watch_bot.db.repositories import ListingRepository, WatchRepository
from car_watch_bot.services.digest_service import DigestService


logger = logging.getLogger(__name__)


class DigestSender(Protocol):
    """Interface for sending digest payloads."""

    async def send_digest(
        self,
        target: WatchDeliveryTarget,
        digest: DigestPayload,
    ) -> str | None:
        """Send one digest payload and return the resolved thread id."""

    async def send_no_updates(self, target: WatchDeliveryTarget) -> str | None:
        """Send a no-update digest confirmation and return the resolved thread id."""


class NotificationService:
    """Business operations for scheduled digest notifications."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        digest_sender: DigestSender,
    ) -> None:
        self.session_factory = session_factory
        self.digest_sender = digest_sender

    async def send_due_digests(self, now: datetime | None = None) -> int:
        """Send due digest notifications and return sent digest count."""

        current_time = now or datetime.now(timezone.utc)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)

        sent_count = 0
        with self.session_factory() as session:
            watches = WatchRepository(session).list_all_active()
            for watch in watches:
                if not self._watch_is_due(watch, current_time):
                    continue
                if not watch.channel_id:
                    logger.warning("watch has no digest channel", extra={"watch_id": watch.id})
                    continue

                target = _delivery_target(watch)
                digest_service = DigestService(ListingRepository(session))
                digest = digest_service.build_digest(
                    watch,
                    max_listings=watch.digest_max_listings,
                    summary_only=watch.digest_summary_only,
                )
                if digest is None:
                    if not watch.digest_no_update_enabled:
                        continue
                    thread_id = await self.digest_sender.send_no_updates(target)
                    watch.thread_id = thread_id or watch.thread_id
                    watch.last_digest_sent_at = current_time.astimezone(timezone.utc)
                    sent_count += 1
                    continue

                thread_id = await self.digest_sender.send_digest(target, digest)
                watch.thread_id = thread_id or watch.thread_id
                digest_service.mark_digest_sent(
                    watch_id=watch.id,
                    listing_ids=[listing.listing_id for listing in digest.listings],
                )
                watch.last_digest_sent_at = current_time.astimezone(timezone.utc)
                sent_count += 1
            session.commit()
        return sent_count

    def _watch_is_due(self, watch: Watch, current_time: datetime) -> bool:
        """Return whether a watch should send at the current minute."""

        local_time = self._watch_local_time(watch, current_time)
        if _is_in_quiet_hours(
            local_time.time(),
            watch.digest_quiet_hours_start,
            watch.digest_quiet_hours_end,
        ):
            return False

        frequency_minutes = _digest_frequency_minutes(watch)
        if not _matches_frequency_slot(
            local_time=local_time,
            notification_time=watch.notification_time,
            frequency_minutes=frequency_minutes,
        ):
            return False

        if watch.last_digest_sent_at is None:
            return True

        last_sent = watch.last_digest_sent_at
        if last_sent.tzinfo is None:
            last_sent = last_sent.replace(tzinfo=timezone.utc)
        local_current_minute = local_time.replace(second=0, microsecond=0)
        local_last_sent = last_sent.astimezone(local_time.tzinfo).replace(
            second=0,
            microsecond=0,
        )
        elapsed_minutes = (local_current_minute - local_last_sent).total_seconds() / 60
        return elapsed_minutes >= frequency_minutes

    def _watch_local_time(self, watch: Watch, current_time: datetime) -> datetime:
        """Return current time in the watch timezone, with a safe fallback."""

        try:
            return current_time.astimezone(ZoneInfo(watch.timezone))
        except ZoneInfoNotFoundError:
            logger.warning("invalid watch timezone", extra={"watch_id": watch.id})
            return current_time.astimezone(ZoneInfo("Australia/Sydney"))


def _delivery_target(watch: Watch) -> WatchDeliveryTarget:
    """Create interface-neutral delivery target details for a scheduled watch."""

    if watch.channel_id is None:
        raise ValueError("watch channel_id is required")
    return WatchDeliveryTarget(
        watch_id=watch.id,
        watch_name=watch.name,
        watch_query=watch.query,
        included_keywords=list(watch.included_keywords),
        channel_id=watch.channel_id,
        thread_id=watch.thread_id,
    )


def _digest_frequency_minutes(watch: Watch) -> int:
    """Return a valid digest frequency for a persisted watch."""

    frequency_minutes = watch.digest_frequency_minutes or 1440
    if frequency_minutes < 1:
        logger.warning(
            "invalid digest frequency",
            extra={"watch_id": watch.id, "digest_frequency_minutes": frequency_minutes},
        )
        return 1440
    return frequency_minutes


def _matches_frequency_slot(
    local_time: datetime,
    notification_time: time,
    frequency_minutes: int,
) -> bool:
    """Return whether the current local minute is a digest slot."""

    current_minute = local_time.hour * 60 + local_time.minute
    notification_minute = notification_time.hour * 60 + notification_time.minute
    if frequency_minutes > 1440:
        return current_minute == notification_minute
    return (current_minute - notification_minute) % frequency_minutes == 0


def _is_in_quiet_hours(
    current_time: time,
    quiet_start: time | None,
    quiet_end: time | None,
) -> bool:
    """Return whether a local time is inside a quiet-hours window."""

    if quiet_start is None or quiet_end is None:
        return False
    current_minute = current_time.hour * 60 + current_time.minute
    start_minute = quiet_start.hour * 60 + quiet_start.minute
    end_minute = quiet_end.hour * 60 + quiet_end.minute
    if start_minute < end_minute:
        return start_minute <= current_minute < end_minute
    return current_minute >= start_minute or current_minute < end_minute
