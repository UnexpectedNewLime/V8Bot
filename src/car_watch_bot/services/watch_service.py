"""Watch service for Discord and future interface layers."""

from dataclasses import dataclass
from datetime import time

from sqlalchemy.orm import Session, sessionmaker

from car_watch_bot.core.models import WatchDeliveryTarget
from car_watch_bot.db.models import Watch
from car_watch_bot.db.repositories import SourceRepository, UserRepository, WatchRepository


class WatchServiceError(Exception):
    """Base exception for watch service failures."""


class WatchValidationError(WatchServiceError):
    """Raised when watch input is invalid."""


class WatchNotFoundError(WatchServiceError):
    """Raised when a watch does not exist or is not owned by the user."""


@dataclass(frozen=True)
class WatchSummary:
    """Watch data safe for interface presentation."""

    watch_id: int
    car_query: str
    keywords: list[str]
    exclude_keywords: list[str]
    notify_time: str
    preferred_currency: str
    distance_unit: str
    active_sources_count: int


class WatchService:
    """Business operations for watches."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        default_timezone: str = "Australia/Sydney",
        default_currency: str = "AUD",
        default_distance_unit: str = "km",
    ) -> None:
        self.session_factory = session_factory
        self.default_timezone = default_timezone
        self.default_currency = default_currency
        self.default_distance_unit = default_distance_unit

    def create_watch(
        self,
        discord_user_id: str,
        car_query: str,
        keywords: str,
        exclude_keywords: str | None,
        notify_time: str,
        guild_id: str | None = None,
        channel_id: str | None = None,
    ) -> WatchSummary:
        """Create a watch for a Discord user."""

        parsed_keywords = parse_keyword_csv(keywords)
        parsed_exclude_keywords = parse_keyword_csv(
            exclude_keywords or "",
            allow_empty=True,
        )
        parsed_notify_time = parse_notify_time(notify_time)
        normalized_query = car_query.strip()
        if not normalized_query:
            raise WatchValidationError("car_query is required")

        with self.session_factory() as session:
            user = UserRepository(session).get_or_create_by_discord_id(discord_user_id)
            watch = WatchRepository(session).create_watch(
                user_id=user.id,
                name=normalized_query,
                query=normalized_query,
                included_keywords=parsed_keywords,
                excluded_keywords=parsed_exclude_keywords,
                notification_time=parsed_notify_time,
                guild_id=guild_id,
                channel_id=channel_id,
                preferred_currency=self.default_currency,
                distance_unit=self.default_distance_unit,
                timezone=self.default_timezone,
            )
            summary = self._watch_summary(watch, active_sources_count=0)
            session.commit()
            return summary

    def list_watches(self, discord_user_id: str) -> list[WatchSummary]:
        """List active watches owned by a Discord user."""

        with self.session_factory() as session:
            user = UserRepository(session).get_or_create_by_discord_id(discord_user_id)
            watches = WatchRepository(session).list_active_for_user(user.id)
            summaries = [
                self._watch_summary(watch, self._active_sources_count(watch))
                for watch in watches
            ]
            session.commit()
            return summaries

    def deactivate_watch(self, discord_user_id: str, watch_id: int) -> None:
        """Deactivate a watch if it belongs to the Discord user."""

        with self.session_factory() as session:
            user = UserRepository(session).get_or_create_by_discord_id(discord_user_id)
            watch_repository = WatchRepository(session)
            watch = watch_repository.get_active_for_user(watch_id, user.id)
            if watch is None:
                raise WatchNotFoundError("watch not found")
            watch_repository.deactivate_watch(watch.id)
            session.commit()

    def add_keyword(self, discord_user_id: str, watch_id: int, keyword: str) -> WatchSummary:
        """Add an included keyword to a user's watch."""

        normalized_keyword = _normalize_single_keyword(keyword)
        with self.session_factory() as session:
            watch = self._get_owned_watch(session, discord_user_id, watch_id)
            if normalized_keyword not in watch.included_keywords:
                watch.included_keywords = [*watch.included_keywords, normalized_keyword]
                watch.criteria_version += 1
            summary = self._watch_summary(watch, self._active_sources_count(watch))
            session.commit()
            return summary

    def remove_keyword(
        self,
        discord_user_id: str,
        watch_id: int,
        keyword: str,
    ) -> WatchSummary:
        """Remove an included keyword from a user's watch."""

        normalized_keyword = _normalize_single_keyword(keyword)
        with self.session_factory() as session:
            watch = self._get_owned_watch(session, discord_user_id, watch_id)
            remaining_keywords = [
                existing_keyword
                for existing_keyword in watch.included_keywords
                if existing_keyword.casefold() != normalized_keyword.casefold()
            ]
            if not remaining_keywords:
                raise WatchValidationError("watch must keep at least one keyword")
            if len(remaining_keywords) != len(watch.included_keywords):
                watch.included_keywords = remaining_keywords
                watch.criteria_version += 1
            summary = self._watch_summary(watch, self._active_sources_count(watch))
            session.commit()
            return summary

    def add_exclude_keyword(
        self,
        discord_user_id: str,
        watch_id: int,
        keyword: str,
    ) -> WatchSummary:
        """Add an excluded keyword to a user's watch."""

        normalized_keyword = _normalize_single_keyword(keyword)
        with self.session_factory() as session:
            watch = self._get_owned_watch(session, discord_user_id, watch_id)
            if normalized_keyword not in watch.excluded_keywords:
                watch.excluded_keywords = [*watch.excluded_keywords, normalized_keyword]
                watch.criteria_version += 1
            summary = self._watch_summary(watch, self._active_sources_count(watch))
            session.commit()
            return summary

    def remove_exclude_keyword(
        self,
        discord_user_id: str,
        watch_id: int,
        keyword: str,
    ) -> WatchSummary:
        """Remove an excluded keyword from a user's watch."""

        normalized_keyword = _normalize_single_keyword(keyword)
        with self.session_factory() as session:
            watch = self._get_owned_watch(session, discord_user_id, watch_id)
            remaining_keywords = [
                existing_keyword
                for existing_keyword in watch.excluded_keywords
                if existing_keyword.casefold() != normalized_keyword.casefold()
            ]
            if len(remaining_keywords) != len(watch.excluded_keywords):
                watch.excluded_keywords = remaining_keywords
                watch.criteria_version += 1
            summary = self._watch_summary(watch, self._active_sources_count(watch))
            session.commit()
            return summary

    def update_notify_time(
        self,
        discord_user_id: str,
        watch_id: int,
        notify_time: str,
    ) -> WatchSummary:
        """Update a watch notification time."""

        parsed_notify_time = parse_notify_time(notify_time)
        with self.session_factory() as session:
            watch = self._get_owned_watch(session, discord_user_id, watch_id)
            watch.notification_time = parsed_notify_time
            summary = self._watch_summary(watch, self._active_sources_count(watch))
            session.commit()
            return summary

    def update_currency(
        self,
        discord_user_id: str,
        watch_id: int,
        currency: str,
    ) -> WatchSummary:
        """Update a watch preferred currency."""

        normalized_currency = currency.strip().upper()
        if len(normalized_currency) != 3 or not normalized_currency.isalpha():
            raise WatchValidationError("currency must be a three-letter code")
        with self.session_factory() as session:
            watch = self._get_owned_watch(session, discord_user_id, watch_id)
            watch.preferred_currency = normalized_currency
            summary = self._watch_summary(watch, self._active_sources_count(watch))
            session.commit()
            return summary

    def update_distance_unit(
        self,
        discord_user_id: str,
        watch_id: int,
        distance_unit: str,
    ) -> WatchSummary:
        """Update a watch distance unit."""

        normalized_unit = distance_unit.strip().lower()
        if normalized_unit not in {"km", "mi"}:
            raise WatchValidationError("distance_unit must be km or mi")
        with self.session_factory() as session:
            watch = self._get_owned_watch(session, discord_user_id, watch_id)
            watch.distance_unit = normalized_unit
            summary = self._watch_summary(watch, self._active_sources_count(watch))
            session.commit()
            return summary

    def add_source_to_watch(
        self,
        discord_user_id: str,
        watch_id: int,
        source_id: int,
    ) -> None:
        """Attach a source to a user's watch."""

        with self.session_factory() as session:
            user = UserRepository(session).get_or_create_by_discord_id(discord_user_id)
            watch = WatchRepository(session).get_active_for_user(watch_id, user.id)
            if watch is None:
                raise WatchNotFoundError("watch not found")
            SourceRepository(session).add_source_to_watch(watch.id, source_id)
            session.commit()

    def get_delivery_target(
        self,
        discord_user_id: str,
        watch_id: int,
    ) -> WatchDeliveryTarget:
        """Return watch-specific delivery details for an owned active watch."""

        with self.session_factory() as session:
            watch = self._get_owned_watch(session, discord_user_id, watch_id)
            target = self._delivery_target(watch)
            session.commit()
            return target

    def set_thread_id(
        self,
        discord_user_id: str,
        watch_id: int,
        thread_id: str | None,
    ) -> WatchDeliveryTarget:
        """Persist a Discord thread id for an owned active watch."""

        with self.session_factory() as session:
            user = UserRepository(session).get_or_create_by_discord_id(discord_user_id)
            watch_repository = WatchRepository(session)
            watch = watch_repository.get_active_for_user(watch_id, user.id)
            if watch is None:
                raise WatchNotFoundError("watch not found")
            watch_repository.set_thread_id(watch.id, thread_id)
            target = self._delivery_target(watch)
            session.commit()
            return target

    def set_starred_thread_id(
        self,
        discord_user_id: str,
        watch_id: int,
        thread_id: str | None,
    ) -> WatchDeliveryTarget:
        """Persist a Discord starred thread id for an owned active watch."""

        with self.session_factory() as session:
            user = UserRepository(session).get_or_create_by_discord_id(discord_user_id)
            watch_repository = WatchRepository(session)
            watch = watch_repository.get_active_for_user(watch_id, user.id)
            if watch is None:
                raise WatchNotFoundError("watch not found")
            watch_repository.set_starred_thread_id(watch.id, thread_id)
            target = self._delivery_target(watch)
            session.commit()
            return target

    def _get_owned_watch(
        self,
        session: Session,
        discord_user_id: str,
        watch_id: int,
    ) -> Watch:
        """Return an active watch owned by a Discord user."""

        user = UserRepository(session).get_or_create_by_discord_id(discord_user_id)
        watch = WatchRepository(session).get_active_for_user(watch_id, user.id)
        if watch is None:
            raise WatchNotFoundError("watch not found")
        return watch

    def _delivery_target(self, watch: Watch) -> WatchDeliveryTarget:
        """Create interface-neutral watch delivery details."""

        if watch.channel_id is None:
            raise WatchValidationError("watch has no delivery channel")
        return WatchDeliveryTarget(
            watch_id=watch.id,
            watch_name=watch.name,
            watch_query=watch.query,
            included_keywords=list(watch.included_keywords),
            channel_id=watch.channel_id,
            thread_id=watch.thread_id,
            starred_thread_id=watch.starred_thread_id,
        )

    def _watch_summary(self, watch: Watch, active_sources_count: int) -> WatchSummary:
        """Create an interface-safe watch summary."""

        return WatchSummary(
            watch_id=watch.id,
            car_query=watch.query,
            keywords=list(watch.included_keywords),
            exclude_keywords=list(watch.excluded_keywords),
            notify_time=watch.notification_time.strftime("%H:%M"),
            preferred_currency=watch.preferred_currency,
            distance_unit=watch.distance_unit,
            active_sources_count=active_sources_count,
        )

    def _active_sources_count(self, watch: Watch) -> int:
        """Count active enabled sources on a loaded watch."""

        return sum(
            1
            for watch_source in watch.watch_sources
            if watch_source.is_enabled and watch_source.source.is_active
        )


def parse_keyword_csv(raw_keywords: str, allow_empty: bool = False) -> list[str]:
    """Parse comma-separated keywords."""

    keywords = [
        keyword.strip()
        for keyword in raw_keywords.split(",")
        if keyword.strip()
    ]
    if not keywords and not allow_empty:
        raise WatchValidationError("at least one keyword is required")
    return keywords


def _normalize_single_keyword(keyword: str) -> str:
    """Normalize one keyword input."""

    normalized_keyword = keyword.strip()
    if not normalized_keyword:
        raise WatchValidationError("keyword is required")
    if "," in normalized_keyword:
        raise WatchValidationError("keyword must not contain commas")
    return normalized_keyword


def parse_notify_time(raw_notify_time: str) -> time:
    """Parse an HH:MM notification time."""

    try:
        hour_text, minute_text = raw_notify_time.split(":", maxsplit=1)
        if len(hour_text) != 2 or len(minute_text) != 2:
            raise ValueError
        hour = int(hour_text)
        minute = int(minute_text)
        return time(hour=hour, minute=minute)
    except ValueError as exc:
        raise WatchValidationError("notify_time must use HH:MM format") from exc
