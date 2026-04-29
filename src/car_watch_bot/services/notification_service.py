"""Notification service for scheduled digests."""

import logging
from datetime import datetime, timezone
from typing import Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session, sessionmaker

from car_watch_bot.core.models import DigestPayload
from car_watch_bot.db.models import Watch
from car_watch_bot.db.repositories import ListingRepository, WatchRepository
from car_watch_bot.services.digest_service import DigestService


logger = logging.getLogger(__name__)


class DigestSender(Protocol):
    """Interface for sending digest payloads."""

    async def send_digest(self, channel_id: str, digest: DigestPayload) -> None:
        """Send one digest payload."""


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

                digest_service = DigestService(ListingRepository(session))
                digest = digest_service.build_digest(watch)
                if digest is None:
                    continue

                await self.digest_sender.send_digest(watch.channel_id, digest)
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

        try:
            local_time = current_time.astimezone(ZoneInfo(watch.timezone))
        except ZoneInfoNotFoundError:
            logger.warning("invalid watch timezone", extra={"watch_id": watch.id})
            local_time = current_time.astimezone(ZoneInfo("Australia/Sydney"))

        if local_time.hour != watch.notification_time.hour:
            return False
        if local_time.minute != watch.notification_time.minute:
            return False
        if watch.last_digest_sent_at is None:
            return True

        last_sent = watch.last_digest_sent_at
        if last_sent.tzinfo is None:
            last_sent = last_sent.replace(tzinfo=timezone.utc)
        local_last_sent = last_sent.astimezone(local_time.tzinfo)
        return not (
            local_last_sent.date() == local_time.date()
            and local_last_sent.hour == local_time.hour
            and local_last_sent.minute == local_time.minute
        )
