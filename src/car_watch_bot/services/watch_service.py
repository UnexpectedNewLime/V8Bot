"""Watch service for Discord and future interface layers."""

from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session, sessionmaker

from car_watch_bot.core.models import WatchDeliveryTarget
from car_watch_bot.db.models import Watch
from car_watch_bot.db.repositories import SourceRepository, UserRepository, WatchRepository

MIN_DIGEST_FREQUENCY_MINUTES = 1
MAX_DIGEST_FREQUENCY_MINUTES = 10080
MAX_DIGEST_LISTINGS_LIMIT = 50


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


@dataclass(frozen=True)
class WatchDigestControls:
    """Per-watch digest controls safe for interface presentation."""

    watch_id: int
    car_query: str
    no_update_messages: bool
    max_listings: int | None
    summary_only: bool
    immediate_alerts: bool
    quiet_hours_start: str | None
    quiet_hours_end: str | None
    digest_frequency_minutes: int


@dataclass(frozen=True)
class WatchSourceDetails:
    """Source details safe for watch configuration presentation."""

    source_id: int
    name: str
    kind: str
    base_url: str | None
    is_enabled: bool
    is_active: bool


@dataclass(frozen=True)
class WatchDetails:
    """Detailed watch data safe for interface presentation."""

    watch_id: int
    name: str
    car_query: str
    keywords: list[str]
    exclude_keywords: list[str]
    notify_time: str
    timezone: str
    preferred_currency: str
    distance_unit: str
    guild_id: str | None
    channel_id: str | None
    thread_id: str | None
    criteria_version: int
    is_active: bool
    active_sources_count: int
    sources: list[WatchSourceDetails]


@dataclass(frozen=True)
class WatchUpdateRequest:
    """Editable watch fields where None means leave the field unchanged."""

    name: str | None = None
    car_query: str | None = None
    keywords: str | None = None
    exclude_keywords: str | None = None
    clear_exclusions: bool = False
    notify_time: str | None = None
    timezone: str | None = None
    currency: str | None = None
    distance_unit: str | None = None
    guild_id: str | None = None
    channel_id: str | None = None
    thread_id: str | None = None
    clear_channel: bool = False
    clear_thread: bool = False
    is_active: bool | None = None


@dataclass(frozen=True)
class WatchUpdateResult:
    """Result of a consolidated watch edit."""

    details: WatchDetails
    changed_fields: list[str]


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

    def get_watch_details(self, discord_user_id: str, watch_id: int) -> WatchDetails:
        """Return a detailed owned watch view, including inactive watches."""

        with self.session_factory() as session:
            watch = self._get_owned_watch(
                session,
                discord_user_id,
                watch_id,
                include_inactive=True,
            )
            details = self._watch_details(watch)
            session.commit()
            return details

    def update_watch(
        self,
        discord_user_id: str,
        watch_id: int,
        update: WatchUpdateRequest,
    ) -> WatchUpdateResult:
        """Update any editable watch field for an owned watch."""

        _validate_update_flags(update)
        normalized_name = _normalize_optional_text(update.name, "watch_name", 120)
        normalized_query = _normalize_optional_text(update.car_query, "car_query", 240)
        normalized_keywords = (
            parse_keyword_csv(update.keywords)
            if update.keywords is not None
            else None
        )
        normalized_exclude_keywords = (
            parse_keyword_csv(update.exclude_keywords, allow_empty=True)
            if update.exclude_keywords is not None
            else None
        )
        normalized_notify_time = (
            parse_notify_time(update.notify_time)
            if update.notify_time is not None
            else None
        )
        normalized_timezone = _normalize_optional_timezone(update.timezone)
        normalized_currency = _normalize_optional_currency(update.currency)
        normalized_distance_unit = _normalize_optional_distance_unit(update.distance_unit)
        normalized_guild_id = _normalize_optional_discord_id(update.guild_id, "guild_id")
        normalized_channel_id = _normalize_optional_discord_id(
            update.channel_id,
            "channel_id",
        )
        normalized_thread_id = _normalize_optional_discord_id(update.thread_id, "thread_id")

        with self.session_factory() as session:
            watch = self._get_owned_watch(
                session,
                discord_user_id,
                watch_id,
                include_inactive=True,
            )
            changed_fields: list[str] = []
            criteria_changed = False

            if normalized_name is not None and normalized_name != watch.name:
                watch.name = normalized_name
                changed_fields.append("watch_name")

            if normalized_query is not None and normalized_query != watch.query:
                watch.query = normalized_query
                changed_fields.append("car_query")
                criteria_changed = True

            if (
                normalized_keywords is not None
                and normalized_keywords != watch.included_keywords
            ):
                watch.included_keywords = normalized_keywords
                changed_fields.append("keywords")
                criteria_changed = True

            if update.clear_exclusions:
                if watch.excluded_keywords:
                    watch.excluded_keywords = []
                    changed_fields.append("excluded_keywords")
                    criteria_changed = True
            elif (
                normalized_exclude_keywords is not None
                and normalized_exclude_keywords != watch.excluded_keywords
            ):
                watch.excluded_keywords = normalized_exclude_keywords
                changed_fields.append("excluded_keywords")
                criteria_changed = True

            if (
                normalized_notify_time is not None
                and normalized_notify_time != watch.notification_time
            ):
                watch.notification_time = normalized_notify_time
                changed_fields.append("notify_time")

            if normalized_timezone is not None and normalized_timezone != watch.timezone:
                watch.timezone = normalized_timezone
                changed_fields.append("timezone")

            if (
                normalized_currency is not None
                and normalized_currency != watch.preferred_currency
            ):
                watch.preferred_currency = normalized_currency
                changed_fields.append("currency")

            if (
                normalized_distance_unit is not None
                and normalized_distance_unit != watch.distance_unit
            ):
                watch.distance_unit = normalized_distance_unit
                changed_fields.append("distance_unit")

            if normalized_guild_id is not None and normalized_guild_id != watch.guild_id:
                watch.guild_id = normalized_guild_id
                changed_fields.append("guild_id")

            if update.clear_channel:
                if watch.channel_id is not None:
                    watch.channel_id = None
                    changed_fields.append("channel_id")
                if watch.thread_id is not None:
                    watch.thread_id = None
                    changed_fields.append("thread_id")
            elif normalized_channel_id is not None:
                channel_changed = normalized_channel_id != watch.channel_id
                if channel_changed:
                    watch.channel_id = normalized_channel_id
                    changed_fields.append("channel_id")
                    if normalized_thread_id is None and watch.thread_id is not None:
                        watch.thread_id = None
                        changed_fields.append("thread_id")

            if update.clear_thread:
                if watch.thread_id is not None:
                    watch.thread_id = None
                    changed_fields.append("thread_id")
            elif normalized_thread_id is not None:
                if watch.channel_id is None:
                    raise WatchValidationError("thread_id requires a channel_id")
                if normalized_thread_id != watch.thread_id:
                    watch.thread_id = normalized_thread_id
                    changed_fields.append("thread_id")

            if update.is_active is not None and update.is_active != watch.is_active:
                watch.is_active = update.is_active
                watch.deactivated_at = None if update.is_active else datetime.utcnow()
                changed_fields.append("active")

            if criteria_changed:
                watch.criteria_version += 1

            details = self._watch_details(watch)
            session.commit()
            return WatchUpdateResult(details=details, changed_fields=changed_fields)

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

    def get_digest_controls(
        self,
        discord_user_id: str,
        watch_id: int,
    ) -> WatchDigestControls:
        """Return per-watch digest controls for an owned active watch."""

        with self.session_factory() as session:
            watch = self._get_owned_watch(session, discord_user_id, watch_id)
            controls = self._watch_digest_controls(watch)
            session.commit()
            return controls

    def update_digest_controls(
        self,
        discord_user_id: str,
        watch_id: int,
        no_update_messages: bool | None = None,
        max_listings: int | None = None,
        clear_max_listings: bool = False,
        summary_only: bool | None = None,
        immediate_alerts: bool | None = None,
        quiet_hours_start: str | None = None,
        quiet_hours_end: str | None = None,
        clear_quiet_hours: bool = False,
        digest_frequency_minutes: int | None = None,
    ) -> WatchDigestControls:
        """Update per-watch digest controls for an owned active watch."""

        if clear_max_listings and max_listings is not None:
            raise WatchValidationError("choose max_listings or clear_max_listings, not both")
        if max_listings is not None:
            _validate_max_digest_listings(max_listings)
        if digest_frequency_minutes is not None:
            _validate_digest_frequency(digest_frequency_minutes)
        parsed_quiet_hours = _parse_quiet_hours_update(
            quiet_hours_start=quiet_hours_start,
            quiet_hours_end=quiet_hours_end,
            clear_quiet_hours=clear_quiet_hours,
        )

        with self.session_factory() as session:
            watch = self._get_owned_watch(session, discord_user_id, watch_id)
            if no_update_messages is not None:
                watch.digest_no_update_enabled = no_update_messages
            if clear_max_listings:
                watch.digest_max_listings = None
            elif max_listings is not None:
                watch.digest_max_listings = max_listings
            if summary_only is not None:
                watch.digest_summary_only = summary_only
            if immediate_alerts is not None:
                watch.digest_immediate_alerts = immediate_alerts
            if parsed_quiet_hours is not None:
                watch.digest_quiet_hours_start = parsed_quiet_hours[0]
                watch.digest_quiet_hours_end = parsed_quiet_hours[1]
            if digest_frequency_minutes is not None:
                watch.digest_frequency_minutes = digest_frequency_minutes
            controls = self._watch_digest_controls(watch)
            session.commit()
            return controls

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
        *,
        include_inactive: bool = False,
    ) -> Watch:
        """Return a watch owned by a Discord user."""

        user = UserRepository(session).get_or_create_by_discord_id(discord_user_id)
        watch_repository = WatchRepository(session)
        if include_inactive:
            watch = watch_repository.get_for_user(watch_id, user.id)
        else:
            watch = watch_repository.get_active_for_user(watch_id, user.id)
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

    def _watch_digest_controls(self, watch: Watch) -> WatchDigestControls:
        """Create interface-safe digest controls."""

        return WatchDigestControls(
            watch_id=watch.id,
            car_query=watch.query,
            no_update_messages=watch.digest_no_update_enabled,
            max_listings=watch.digest_max_listings,
            summary_only=watch.digest_summary_only,
            immediate_alerts=watch.digest_immediate_alerts,
            quiet_hours_start=_format_optional_time(watch.digest_quiet_hours_start),
            quiet_hours_end=_format_optional_time(watch.digest_quiet_hours_end),
            digest_frequency_minutes=watch.digest_frequency_minutes,
        )

    def _watch_details(self, watch: Watch) -> WatchDetails:
        """Create an interface-safe detailed watch view."""

        sources = [
            WatchSourceDetails(
                source_id=watch_source.source.id,
                name=watch_source.source.name,
                kind=watch_source.source.kind,
                base_url=watch_source.source.base_url,
                is_enabled=watch_source.is_enabled,
                is_active=watch_source.source.is_active,
            )
            for watch_source in sorted(
                watch.watch_sources,
                key=lambda watch_source: watch_source.source.id,
            )
        ]
        return WatchDetails(
            watch_id=watch.id,
            name=watch.name,
            car_query=watch.query,
            keywords=list(watch.included_keywords),
            exclude_keywords=list(watch.excluded_keywords),
            notify_time=watch.notification_time.strftime("%H:%M"),
            timezone=watch.timezone,
            preferred_currency=watch.preferred_currency,
            distance_unit=watch.distance_unit,
            guild_id=watch.guild_id,
            channel_id=watch.channel_id,
            thread_id=watch.thread_id,
            criteria_version=watch.criteria_version,
            is_active=watch.is_active,
            active_sources_count=sum(
                1 for source in sources if source.is_enabled and source.is_active
            ),
            sources=sources,
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


def _validate_max_digest_listings(max_listings: int) -> None:
    """Validate a digest listing cap."""

    if max_listings < 1 or max_listings > MAX_DIGEST_LISTINGS_LIMIT:
        raise WatchValidationError(
            f"max_listings must be between 1 and {MAX_DIGEST_LISTINGS_LIMIT}"
        )


def _validate_digest_frequency(digest_frequency_minutes: int) -> None:
    """Validate digest frequency minutes."""

    if (
        digest_frequency_minutes < MIN_DIGEST_FREQUENCY_MINUTES
        or digest_frequency_minutes > MAX_DIGEST_FREQUENCY_MINUTES
    ):
        raise WatchValidationError(
            "digest_frequency_minutes must be between "
            f"{MIN_DIGEST_FREQUENCY_MINUTES} and {MAX_DIGEST_FREQUENCY_MINUTES}"
        )


def _parse_quiet_hours_update(
    quiet_hours_start: str | None,
    quiet_hours_end: str | None,
    clear_quiet_hours: bool,
) -> tuple[time | None, time | None] | None:
    """Parse a quiet-hours command update."""

    start_text = (quiet_hours_start or "").strip()
    end_text = (quiet_hours_end or "").strip()
    if clear_quiet_hours:
        if start_text or end_text:
            raise WatchValidationError(
                "choose quiet_hours_start/end or clear_quiet_hours, not both"
            )
        return (None, None)
    if not start_text and not end_text:
        return None
    if not start_text or not end_text:
        raise WatchValidationError(
            "quiet_hours_start and quiet_hours_end must be supplied together"
        )
    start = parse_notify_time(start_text)
    end = parse_notify_time(end_text)
    if start == end:
        raise WatchValidationError("quiet hours start and end must be different")
    return (start, end)


def _format_optional_time(value: time | None) -> str | None:
    """Format an optional time for command output."""

    if value is None:
        return None
    return value.strftime("%H:%M")


def _validate_update_flags(update: WatchUpdateRequest) -> None:
    """Validate mutually exclusive watch edit fields."""

    if update.clear_exclusions and update.exclude_keywords is not None:
        raise WatchValidationError(
            "exclude_keywords cannot be set while clear_exclusions is true"
        )
    if update.clear_channel and update.channel_id is not None:
        raise WatchValidationError("channel_id cannot be set while clear_channel is true")
    if update.clear_channel and update.thread_id is not None:
        raise WatchValidationError("thread_id cannot be set while clear_channel is true")
    if update.clear_thread and update.thread_id is not None:
        raise WatchValidationError("thread_id cannot be set while clear_thread is true")


def _normalize_optional_text(
    raw_value: str | None,
    field_name: str,
    max_length: int,
) -> str | None:
    """Normalize an optional non-empty text field."""

    if raw_value is None:
        return None
    normalized_value = raw_value.strip()
    if not normalized_value:
        raise WatchValidationError(f"{field_name} is required")
    if len(normalized_value) > max_length:
        raise WatchValidationError(
            f"{field_name} must be {max_length} characters or fewer"
        )
    return normalized_value


def _normalize_optional_currency(raw_currency: str | None) -> str | None:
    """Normalize an optional ISO-like currency code."""

    if raw_currency is None:
        return None
    normalized_currency = raw_currency.strip().upper()
    if len(normalized_currency) != 3 or not normalized_currency.isalpha():
        raise WatchValidationError("currency must be a three-letter code")
    return normalized_currency


def _normalize_optional_distance_unit(raw_distance_unit: str | None) -> str | None:
    """Normalize an optional watch distance unit."""

    if raw_distance_unit is None:
        return None
    normalized_unit = raw_distance_unit.strip().lower()
    if normalized_unit not in {"km", "mi"}:
        raise WatchValidationError("distance_unit must be km or mi")
    return normalized_unit


def _normalize_optional_timezone(raw_timezone: str | None) -> str | None:
    """Normalize and validate an optional IANA timezone."""

    if raw_timezone is None:
        return None
    normalized_timezone = raw_timezone.strip()
    if not normalized_timezone:
        raise WatchValidationError("timezone is required")
    if len(normalized_timezone) > 64:
        raise WatchValidationError("timezone must be 64 characters or fewer")
    try:
        ZoneInfo(normalized_timezone)
    except ZoneInfoNotFoundError as exc:
        raise WatchValidationError("timezone must be a valid IANA timezone") from exc
    return normalized_timezone


def _normalize_optional_discord_id(
    raw_discord_id: str | None,
    field_name: str,
) -> str | None:
    """Normalize an optional Discord snowflake id."""

    if raw_discord_id is None:
        return None
    normalized_id = raw_discord_id.strip()
    if not normalized_id:
        raise WatchValidationError(f"{field_name} is required")
    if not normalized_id.isdigit():
        raise WatchValidationError(f"{field_name} must be a numeric Discord id")
    if len(normalized_id) > 32:
        raise WatchValidationError(f"{field_name} must be 32 digits or fewer")
    return normalized_id
