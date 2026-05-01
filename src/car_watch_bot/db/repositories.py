"""Database repositories for the local prototype."""

from datetime import datetime, time
from decimal import Decimal
from hashlib import sha256
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from car_watch_bot.core.models import ListingCandidate, ScoreResult
from car_watch_bot.db.models import (
    Listing,
    ScrapeAttempt,
    Source,
    SourceTestAttempt,
    User,
    Watch,
    WatchListing,
    WatchSource,
)


def _content_hash(title: str, url: str) -> str:
    """Create a stable content hash for a listing."""

    return sha256(f"{title.casefold()}|{url}".encode("utf-8")).hexdigest()


FIRST_SEEN_PRICE_AMOUNT_KEY = "v8bot_first_seen_price_amount"
FIRST_SEEN_PRICE_CURRENCY_KEY = "v8bot_first_seen_price_currency"
PREVIOUS_PRICE_AMOUNT_KEY = "v8bot_previous_price_amount"
PREVIOUS_PRICE_CURRENCY_KEY = "v8bot_previous_price_currency"
PRICE_CHANGED_AT_KEY = "v8bot_price_changed_at"


def _listing_raw_payload_for_insert(listing: ListingCandidate) -> dict[str, Any]:
    """Return scraper metadata augmented with V8Bot price history."""

    raw_payload = _payload_dict(listing.raw_payload)
    _set_price_snapshot(
        raw_payload,
        FIRST_SEEN_PRICE_AMOUNT_KEY,
        FIRST_SEEN_PRICE_CURRENCY_KEY,
        listing.price_amount,
        listing.price_currency,
    )
    return raw_payload


def _listing_raw_payload_for_update(
    db_listing: "Listing",
    listing: ListingCandidate,
) -> dict[str, Any]:
    """Return refreshed scraper metadata preserving known price history."""

    raw_payload = _payload_dict(listing.raw_payload)
    existing_payload = _payload_dict(db_listing.raw_payload)
    if _has_price_snapshot(
        existing_payload,
        FIRST_SEEN_PRICE_AMOUNT_KEY,
        FIRST_SEEN_PRICE_CURRENCY_KEY,
    ):
        raw_payload[FIRST_SEEN_PRICE_AMOUNT_KEY] = existing_payload[
            FIRST_SEEN_PRICE_AMOUNT_KEY
        ]
        raw_payload[FIRST_SEEN_PRICE_CURRENCY_KEY] = existing_payload[
            FIRST_SEEN_PRICE_CURRENCY_KEY
        ]
    else:
        _set_price_snapshot(
            raw_payload,
            FIRST_SEEN_PRICE_AMOUNT_KEY,
            FIRST_SEEN_PRICE_CURRENCY_KEY,
            db_listing.price_amount,
            db_listing.price_currency,
        )

    if _price_changed(
        db_listing.price_amount,
        db_listing.price_currency,
        listing.price_amount,
        listing.price_currency,
    ):
        _set_price_snapshot(
            raw_payload,
            PREVIOUS_PRICE_AMOUNT_KEY,
            PREVIOUS_PRICE_CURRENCY_KEY,
            db_listing.price_amount,
            db_listing.price_currency,
        )
        raw_payload[PRICE_CHANGED_AT_KEY] = (
            datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        )
    return raw_payload


def _payload_dict(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Return a mutable JSON object payload."""

    if not isinstance(payload, dict):
        return {}
    return dict(payload)


def _set_price_snapshot(
    payload: dict[str, Any],
    amount_key: str,
    currency_key: str,
    amount: Decimal | None,
    currency: str | None,
) -> None:
    """Store a JSON-safe price snapshot when complete."""

    if amount is None or not currency:
        return
    payload[amount_key] = f"{amount:.2f}"
    payload[currency_key] = currency


def _has_price_snapshot(
    payload: dict[str, Any],
    amount_key: str,
    currency_key: str,
) -> bool:
    """Return whether a payload has a complete price snapshot."""

    return bool(payload.get(amount_key) and payload.get(currency_key))


def _price_changed(
    old_amount: Decimal | None,
    old_currency: str | None,
    new_amount: Decimal | None,
    new_currency: str | None,
) -> bool:
    """Return whether two complete price values differ."""

    if old_amount is None or new_amount is None:
        return False
    if not old_currency or not new_currency:
        return False
    return old_amount != new_amount or old_currency != new_currency


class UserRepository:
    """Persistence operations for users."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_or_create_by_discord_id(self, discord_user_id: str) -> User:
        """Return an existing user or create one by Discord id."""

        user = self.session.scalar(
            select(User).where(User.discord_user_id == discord_user_id)
        )
        if user is not None:
            return user

        user = User(discord_user_id=discord_user_id)
        self.session.add(user)
        self.session.flush()
        return user


class WatchRepository:
    """Persistence operations for watches."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_watch(
        self,
        user_id: int,
        name: str,
        query: str,
        included_keywords: list[str],
        excluded_keywords: list[str] | None = None,
        notification_time: time | None = None,
        guild_id: str | None = None,
        channel_id: str | None = None,
        preferred_currency: str = "AUD",
        distance_unit: str = "km",
        timezone: str = "Australia/Sydney",
    ) -> Watch:
        """Create a watch."""

        watch = Watch(
            user_id=user_id,
            name=name,
            query=query,
            included_keywords=included_keywords,
            excluded_keywords=excluded_keywords or [],
            notification_time=notification_time or time(hour=9),
            guild_id=guild_id,
            channel_id=channel_id,
            preferred_currency=preferred_currency,
            distance_unit=distance_unit,
            timezone=timezone,
        )
        self.session.add(watch)
        self.session.flush()
        return watch

    def list_active_for_user(self, user_id: int) -> list[Watch]:
        """List active watches for a user."""

        return list(
            self.session.scalars(
                select(Watch)
                .options(selectinload(Watch.watch_sources).selectinload(WatchSource.source))
                .where(Watch.user_id == user_id, Watch.is_active.is_(True))
                .order_by(Watch.id)
            )
        )

    def get_active_for_user(self, watch_id: int, user_id: int) -> Watch | None:
        """Return an active watch owned by a user."""

        return self.session.scalar(
            select(Watch)
            .options(selectinload(Watch.watch_sources).selectinload(WatchSource.source))
            .where(
                Watch.id == watch_id,
                Watch.user_id == user_id,
                Watch.is_active.is_(True),
            )
        )

    def get_for_user(self, watch_id: int, user_id: int) -> Watch | None:
        """Return a watch owned by a user, including inactive watches."""

        return self.session.scalar(
            select(Watch)
            .options(selectinload(Watch.watch_sources).selectinload(WatchSource.source))
            .where(
                Watch.id == watch_id,
                Watch.user_id == user_id,
            )
        )

    def list_all_active(self) -> list[Watch]:
        """List all active watches with sources loaded."""

        return list(
            self.session.scalars(
                select(Watch)
                .options(selectinload(Watch.watch_sources).selectinload(WatchSource.source))
                .where(Watch.is_active.is_(True))
                .order_by(Watch.id)
            )
        )

    def deactivate_watch(self, watch_id: int) -> None:
        """Deactivate a watch."""

        watch = self.session.get(Watch, watch_id)
        if watch is None:
            return
        watch.is_active = False
        watch.deactivated_at = datetime.utcnow()
        self.session.flush()

    def set_thread_id(self, watch_id: int, thread_id: str | None) -> Watch | None:
        """Persist the Discord thread id associated with a watch."""

        watch = self.session.get(Watch, watch_id)
        if watch is None:
            return None
        watch.thread_id = thread_id
        self.session.flush()
        return watch


class SourceRepository:
    """Persistence operations for sources and watch-source links."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_source(
        self,
        name: str,
        kind: str = "mock",
        owner_user_id: int | None = None,
        base_url: str | None = None,
    ) -> Source:
        """Create a source."""

        source = Source(
            name=name,
            kind=kind,
            owner_user_id=owner_user_id,
            base_url=base_url,
        )
        self.session.add(source)
        self.session.flush()
        return source

    def get_by_owner_and_name(self, owner_user_id: int, name: str) -> Source | None:
        """Return a source owned by a user with the given name."""

        return self.session.scalar(
            select(Source).where(
                Source.owner_user_id == owner_user_id,
                Source.name == name,
            )
        )

    def add_source_to_watch(self, watch_id: int, source_id: int) -> WatchSource:
        """Add or re-enable a source for a watch."""

        watch_source = self.session.scalar(
            select(WatchSource).where(
                WatchSource.watch_id == watch_id,
                WatchSource.source_id == source_id,
            )
        )
        if watch_source is None:
            watch_source = WatchSource(watch_id=watch_id, source_id=source_id)
            self.session.add(watch_source)
        else:
            watch_source.is_enabled = True
            watch_source.disabled_at = None
        watch = self.session.get(Watch, watch_id)
        if watch is not None:
            watch.criteria_version += 1
        self.session.flush()
        return watch_source

    def disable_source_for_watch(self, watch_id: int, source_id: int) -> bool:
        """Disable a source association for a watch."""

        watch_source = self.session.scalar(
            select(WatchSource).where(
                WatchSource.watch_id == watch_id,
                WatchSource.source_id == source_id,
                WatchSource.is_enabled.is_(True),
            )
        )
        if watch_source is None:
            return False

        watch_source.is_enabled = False
        watch_source.disabled_at = datetime.utcnow()
        watch = self.session.get(Watch, watch_id)
        if watch is not None:
            watch.criteria_version += 1
        self.session.flush()
        return True

    def list_sources_for_watch(self, watch_id: int) -> list[Source]:
        """List active, enabled sources for a watch."""

        return list(
            self.session.scalars(
                select(Source)
                .join(WatchSource)
                .where(
                    WatchSource.watch_id == watch_id,
                    WatchSource.is_enabled.is_(True),
                    Source.is_active.is_(True),
                )
                .order_by(Source.id)
            )
        )

    def deactivate_source(self, source_id: int) -> None:
        """Deactivate a source."""

        source = self.session.get(Source, source_id)
        if source is None:
            return
        source.is_active = False
        source.deactivated_at = datetime.utcnow()
        self.session.flush()


class ListingRepository:
    """Persistence operations for listings and watch deliveries."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def insert_listing_if_new(
        self,
        source_id: int,
        listing: ListingCandidate,
        score_result: ScoreResult,
        converted_price_amount: Decimal | None,
        converted_price_currency: str | None,
        converted_mileage_value: int | None,
        converted_mileage_unit: str | None,
    ) -> tuple[Listing, bool]:
        """Insert a listing if its source URL is new."""

        existing_listing = self.session.scalar(
            select(Listing).where(Listing.source_id == source_id, Listing.url == listing.url)
        )
        if existing_listing is not None:
            self._update_listing(
                existing_listing,
                listing,
                score_result,
                converted_price_amount,
                converted_price_currency,
                converted_mileage_value,
                converted_mileage_unit,
            )
            self.session.flush()
            return existing_listing, False

        db_listing = Listing(
            source_id=source_id,
            external_id=listing.external_id,
            url=listing.url,
            title=listing.title,
            description=listing.description,
            price_amount=listing.price_amount,
            price_currency=listing.price_currency,
            converted_price_amount=converted_price_amount,
            converted_price_currency=converted_price_currency,
            mileage_value=listing.mileage_value,
            mileage_unit=listing.mileage_unit,
            converted_mileage_value=converted_mileage_value,
            converted_mileage_unit=converted_mileage_unit,
            location_text=listing.location_text,
            score=score_result.score,
            score_reasons=score_result.reasons,
            content_hash=_content_hash(listing.title, listing.url),
            raw_payload=_listing_raw_payload_for_insert(listing),
        )
        self.session.add(db_listing)
        self.session.flush()
        return db_listing, True

    def find_existing_listing(
        self,
        source_id: int,
        listing: ListingCandidate,
    ) -> Listing | None:
        """Find a previously stored listing for a candidate."""

        return self.session.scalar(
            select(Listing).where(Listing.source_id == source_id, Listing.url == listing.url)
        )

    def update_listing(
        self,
        db_listing: Listing,
        listing: ListingCandidate,
        score_result: ScoreResult,
        converted_price_amount: Decimal | None,
        converted_price_currency: str | None,
        converted_mileage_value: int | None,
        converted_mileage_unit: str | None,
    ) -> None:
        """Refresh an existing listing from the latest scrape candidate."""

        self._update_listing(
            db_listing,
            listing,
            score_result,
            converted_price_amount,
            converted_price_currency,
            converted_mileage_value,
            converted_mileage_unit,
        )
        self.session.flush()

    def add_listing_to_watch(self, watch: Watch, listing: Listing) -> WatchListing:
        """Create a pending watch-listing row if needed."""

        watch_listing = self.session.scalar(
            select(WatchListing).where(
                WatchListing.watch_id == watch.id,
                WatchListing.listing_id == listing.id,
            )
        )
        if watch_listing is not None:
            if watch_listing.status == "excluded":
                watch_listing.status = "pending_digest"
                watch_listing.sent_at = None
                watch_listing.watch_criteria_version = watch.criteria_version
                self.session.flush()
            return watch_listing

        watch_listing = WatchListing(
            watch_id=watch.id,
            listing_id=listing.id,
            watch_criteria_version=watch.criteria_version,
        )
        self.session.add(watch_listing)
        self.session.flush()
        return watch_listing

    def exclude_listing_for_watch(self, watch: Watch, listing: Listing) -> None:
        """Hide an existing pending watch-listing rejected by current criteria."""

        watch_listing = self.session.scalar(
            select(WatchListing).where(
                WatchListing.watch_id == watch.id,
                WatchListing.listing_id == listing.id,
            )
        )
        if watch_listing is None or watch_listing.status != "pending_digest":
            return
        watch_listing.status = "excluded"
        watch_listing.watch_criteria_version = watch.criteria_version
        self.session.flush()

    def list_unnotified_for_watch(self, watch_id: int) -> list[Listing]:
        """List pending listings for a watch."""

        return list(
            self.session.scalars(
                select(Listing)
                .join(WatchListing)
                .where(
                    WatchListing.watch_id == watch_id,
                    WatchListing.status == "pending_digest",
                )
                .order_by(Listing.id)
            )
        )

    def list_visible_for_watch(self, watch_id: int) -> list[Listing]:
        """List watch listings that are not excluded by current criteria."""

        return list(
            self.session.scalars(
                select(Listing)
                .join(WatchListing)
                .where(
                    WatchListing.watch_id == watch_id,
                    WatchListing.status.in_(["pending_digest", "sent"]),
                )
                .order_by(Listing.id)
            )
        )

    def list_unnotified_for_watch_listing_ids(
        self,
        watch_id: int,
        listing_ids: list[int],
    ) -> list[Listing]:
        """List selected pending listings for a watch."""

        if not listing_ids:
            return []
        return list(
            self.session.scalars(
                select(Listing)
                .join(WatchListing)
                .where(
                    WatchListing.watch_id == watch_id,
                    WatchListing.status == "pending_digest",
                    Listing.id.in_(listing_ids),
                )
                .order_by(Listing.id)
            )
        )

    def _update_listing(
        self,
        db_listing: Listing,
        listing: ListingCandidate,
        score_result: ScoreResult,
        converted_price_amount: Decimal | None,
        converted_price_currency: str | None,
        converted_mileage_value: int | None,
        converted_mileage_unit: str | None,
    ) -> None:
        """Refresh fields that can change between scrape attempts."""

        db_listing.external_id = listing.external_id
        db_listing.title = listing.title
        db_listing.description = listing.description
        db_listing.price_amount = listing.price_amount
        db_listing.price_currency = listing.price_currency
        db_listing.converted_price_amount = converted_price_amount
        db_listing.converted_price_currency = converted_price_currency
        db_listing.mileage_value = listing.mileage_value
        db_listing.mileage_unit = listing.mileage_unit
        db_listing.converted_mileage_value = converted_mileage_value
        db_listing.converted_mileage_unit = converted_mileage_unit
        db_listing.location_text = listing.location_text
        db_listing.score = score_result.score
        db_listing.score_reasons = score_result.reasons
        db_listing.content_hash = _content_hash(listing.title, listing.url)
        db_listing.raw_payload = _listing_raw_payload_for_update(db_listing, listing)
        db_listing.last_seen_at = datetime.utcnow()

    def mark_listings_as_notified(self, watch_id: int, listing_ids: list[int]) -> None:
        """Mark watch listings as sent."""

        if not listing_ids:
            return
        watch_listings = self.session.scalars(
            select(WatchListing).where(
                WatchListing.watch_id == watch_id,
                WatchListing.listing_id.in_(listing_ids),
                WatchListing.status == "pending_digest",
            )
        )
        for watch_listing in watch_listings:
            watch_listing.status = "sent"
            watch_listing.sent_at = datetime.utcnow()
        self.session.flush()


class ScrapeAttemptRepository:
    """Persistence operations for scrape attempts."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_attempt(
        self,
        watch_id: int,
        source_id: int,
        status: str,
        adapter_kind: str,
        listings_seen: int = 0,
        listings_matched: int = 0,
        listings_created: int = 0,
        error_message: str | None = None,
    ) -> ScrapeAttempt:
        """Create a scrape attempt record."""

        attempt = ScrapeAttempt(
            watch_id=watch_id,
            source_id=source_id,
            status=status,
            adapter_kind=adapter_kind,
            listings_seen=listings_seen,
            listings_matched=listings_matched,
            listings_created=listings_created,
            error_message=error_message,
            finished_at=datetime.utcnow(),
        )
        self.session.add(attempt)
        self.session.flush()
        return attempt


class SourceTestAttemptRepository:
    """Persistence operations for source test attempts."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_attempt(
        self,
        user_id: int,
        url: str,
        status: str,
        notes: list[str],
        detected_links: list[str],
        source_id: int | None = None,
        error_message: str | None = None,
    ) -> SourceTestAttempt:
        """Create a source test attempt."""

        attempt = SourceTestAttempt(
            user_id=user_id,
            source_id=source_id,
            url=url,
            status=status,
            notes=notes,
            detected_links=detected_links,
            error_message=error_message,
            finished_at=datetime.utcnow(),
        )
        self.session.add(attempt)
        self.session.flush()
        return attempt
