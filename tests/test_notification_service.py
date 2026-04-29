"""Tests for scheduled digest notifications."""

import asyncio
from datetime import datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from car_watch_bot.core.models import DigestPayload
from car_watch_bot.db.repositories import (
    ListingRepository,
    ScrapeAttemptRepository,
    SourceRepository,
    UserRepository,
    WatchRepository,
)
from car_watch_bot.scrapers.mock import MockScraper
from car_watch_bot.services.notification_service import NotificationService
from car_watch_bot.services.scrape_service import ScrapeService


class FakeDigestSender:
    """Digest sender test double."""

    def __init__(self) -> None:
        self.sent_digests: list[tuple[str, DigestPayload]] = []

    async def send_digest(self, channel_id: str, digest: DigestPayload) -> None:
        """Record a sent digest."""

        self.sent_digests.append((channel_id, digest))


def _seed_due_watch_with_listings(db_session_factory) -> int:
    with db_session_factory() as session:
        user = UserRepository(session).get_or_create_by_discord_id("123")
        watch = WatchRepository(session).create_watch(
            user_id=user.id,
            name="C5 digest",
            query="C5 Corvette",
            included_keywords=["manual", "HUD", "targa"],
            excluded_keywords=["automatic", "convertible"],
            notification_time=time(hour=9, minute=30),
            channel_id="999",
            timezone="Australia/Sydney",
        )
        source = SourceRepository(session).create_source(name="Mock Cars", kind="mock")
        SourceRepository(session).add_source_to_watch(watch.id, source.id)
        scrape_service = ScrapeService(
            watch_repository=WatchRepository(session),
            source_repository=SourceRepository(session),
            listing_repository=ListingRepository(session),
            scrape_attempt_repository=ScrapeAttemptRepository(session),
            scraper_adapters={"mock": MockScraper()},
            usd_to_aud_rate=Decimal("1.50"),
        )
        asyncio.run(scrape_service.run_once())
        watch_id = watch.id
        session.commit()
        return watch_id


def test_due_digest_sends_and_marks_listings_notified(db_session_factory) -> None:
    watch_id = _seed_due_watch_with_listings(db_session_factory)
    sender = FakeDigestSender()
    service = NotificationService(db_session_factory, sender)
    now = datetime(2026, 4, 28, 9, 30, tzinfo=ZoneInfo("Australia/Sydney"))

    sent_count = asyncio.run(service.send_due_digests(now))

    with db_session_factory() as session:
        pending = ListingRepository(session).list_unnotified_for_watch(watch_id)
    assert sent_count == 1
    assert len(sender.sent_digests) == 1
    assert sender.sent_digests[0][0] == "999"
    assert sender.sent_digests[0][1].listing_count == 3
    assert pending == []


def test_digest_is_not_sent_when_watch_time_is_not_due(db_session_factory) -> None:
    _seed_due_watch_with_listings(db_session_factory)
    sender = FakeDigestSender()
    service = NotificationService(db_session_factory, sender)
    now = datetime(2026, 4, 28, 9, 29, tzinfo=ZoneInfo("Australia/Sydney"))

    sent_count = asyncio.run(service.send_due_digests(now))

    assert sent_count == 0
    assert sender.sent_digests == []


def test_empty_digest_is_not_sent(db_session_factory) -> None:
    with db_session_factory() as session:
        user = UserRepository(session).get_or_create_by_discord_id("123")
        WatchRepository(session).create_watch(
            user_id=user.id,
            name="Empty digest",
            query="C5 Corvette",
            included_keywords=["manual"],
            notification_time=time(hour=9, minute=30),
            channel_id="999",
            timezone="Australia/Sydney",
        )
        session.commit()
    sender = FakeDigestSender()
    service = NotificationService(db_session_factory, sender)
    now = datetime(2026, 4, 28, 9, 30, tzinfo=ZoneInfo("Australia/Sydney"))

    sent_count = asyncio.run(service.send_due_digests(now))

    assert sent_count == 0
    assert sender.sent_digests == []
