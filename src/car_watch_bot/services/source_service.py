"""Source service for source management and source test behaviour."""

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session, sessionmaker

from car_watch_bot.core.models import ListingCandidate, SourceTestResult
from car_watch_bot.db.models import Source
from car_watch_bot.db.repositories import (
    SourceRepository,
    SourceTestAttemptRepository,
    UserRepository,
    WatchRepository,
)
from car_watch_bot.scrapers.base import ScraperAdapter, ScrapeRequest
from car_watch_bot.scrapers.diagnostic import DiagnosticScraper
from car_watch_bot.scrapers.mock import MockScraper
from car_watch_bot.services.watch_service import WatchNotFoundError


class SourceServiceError(Exception):
    """Base exception for source service failures."""


class SourceValidationError(SourceServiceError):
    """Raised when source input is invalid."""


class SourceNotFoundError(SourceServiceError):
    """Raised when a watch-source association is not found."""


@dataclass(frozen=True)
class SourceSummary:
    """Source data safe for interface presentation."""

    source_id: int
    name: str
    kind: str
    base_url: str | None


@dataclass(frozen=True)
class SourceAddResult:
    """Result returned after creating and testing a source."""

    source: SourceSummary
    source_test: SourceTestResult


@dataclass(frozen=True)
class _SourceNameInput:
    """Normalized source name plus whether it was generated."""

    name: str
    is_generated: bool


class SourceService:
    """Business operations for sources."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        source_test_scraper: ScraperAdapter | None = None,
        source_test_scrapers: dict[str, ScraperAdapter] | None = None,
        source_diagnostic_scraper: ScraperAdapter | None = None,
        allow_unregistered_sources: bool = True,
    ) -> None:
        self.session_factory = session_factory
        self.source_test_scraper = source_test_scraper or MockScraper()
        self.source_test_scrapers = source_test_scrapers or {}
        self.source_diagnostic_scraper = source_diagnostic_scraper or DiagnosticScraper(
            user_agent="V8Bot diagnostic"
        )
        self.allow_unregistered_sources = allow_unregistered_sources

    async def add_source_to_watch(
        self,
        discord_user_id: str,
        watch_id: int,
        name: str | None,
        url: str,
    ) -> SourceAddResult:
        """Create a custom source, attach it to a watch, and run a source test."""

        parsed_url = urlparse(url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise SourceValidationError("URL must be http or https")
        source_name = _normalize_source_name(name, url)
        normalized_name = source_name.name
        source_kind = _source_kind_for_url(url)
        existing_source_id: int | None = None
        with self.session_factory() as session:
            user = UserRepository(session).get_or_create_by_discord_id(discord_user_id)
            watch = WatchRepository(session).get_active_for_user(watch_id, user.id)
            if watch is None:
                raise WatchNotFoundError("watch not found")
            source_repository = SourceRepository(session)
            if source_name.is_generated:
                normalized_name = _unique_generated_source_name(
                    source_repository,
                    user.id,
                    source_name.name,
                    url,
                    source_kind,
                )
            existing_source = source_repository.get_by_owner_and_name(user.id, normalized_name)
            if existing_source is not None:
                if existing_source.kind != source_kind or existing_source.base_url != url:
                    raise SourceValidationError(
                        "source name already exists with a different URL or kind"
                    )
                existing_source_id = existing_source.id
            session.commit()

        source_test = await self._run_source_test(
            url,
            source_kind,
            allow_diagnostic=False,
        )
        with self.session_factory() as session:
            user = UserRepository(session).get_or_create_by_discord_id(discord_user_id)
            if not source_test.url_accepted:
                self._record_source_test(session, user.id, url, source_test)
                session.commit()
                raise SourceValidationError("; ".join(source_test.errors))
            watch = WatchRepository(session).get_active_for_user(watch_id, user.id)
            if watch is None:
                raise WatchNotFoundError("watch not found")
            if existing_source_id is None:
                source = SourceRepository(session).create_source(
                    name=normalized_name,
                    kind=source_kind,
                    owner_user_id=user.id,
                    base_url=url,
                )
            else:
                source = session.get(Source, existing_source_id)
                if source is None:
                    raise SourceValidationError("source no longer exists")
            SourceRepository(session).add_source_to_watch(watch.id, source.id)
            self._record_source_test(session, user.id, url, source_test, source.id)
            summary = self._source_summary(source)
            session.commit()
            return SourceAddResult(source=summary, source_test=source_test)

    def list_sources_for_watch(
        self,
        discord_user_id: str,
        watch_id: int,
    ) -> list[SourceSummary]:
        """List sources attached to a user's watch."""

        with self.session_factory() as session:
            user = UserRepository(session).get_or_create_by_discord_id(discord_user_id)
            watch = WatchRepository(session).get_active_for_user(watch_id, user.id)
            if watch is None:
                raise WatchNotFoundError("watch not found")
            sources = SourceRepository(session).list_sources_for_watch(watch.id)
            summaries = [self._source_summary(source) for source in sources]
            session.commit()
            return summaries

    def remove_source_from_watch(
        self,
        discord_user_id: str,
        watch_id: int,
        source_id: int,
    ) -> None:
        """Disable a source association for a user's watch."""

        with self.session_factory() as session:
            user = UserRepository(session).get_or_create_by_discord_id(discord_user_id)
            watch = WatchRepository(session).get_active_for_user(watch_id, user.id)
            if watch is None:
                raise WatchNotFoundError("watch not found")
            was_removed = SourceRepository(session).disable_source_for_watch(
                watch.id,
                source_id,
            )
            if not was_removed:
                raise SourceNotFoundError("source not found for watch")
            session.commit()

    async def test_source_url(
        self,
        discord_user_id: str,
        url: str,
    ) -> SourceTestResult:
        """Test a source URL."""

        source_kind = _source_kind_for_url(url)
        source_test = await self._run_source_test(
            url,
            source_kind,
            allow_diagnostic=True,
        )
        with self.session_factory() as session:
            user = UserRepository(session).get_or_create_by_discord_id(discord_user_id)
            self._record_source_test(session, user.id, url, source_test)
            session.commit()
            return source_test

    async def _run_source_test(
        self,
        url: str,
        source_kind: str,
        *,
        allow_diagnostic: bool,
    ) -> SourceTestResult:
        """Run source test checks."""

        parsed_url = urlparse(url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            return _failed_source_test("URL must be http or https")
        if "facebook.com" in parsed_url.netloc.casefold():
            return _failed_source_test("Facebook Marketplace is not supported")

        scraper = self.source_test_scrapers.get(source_kind)
        if scraper is None:
            if allow_diagnostic:
                scraper = self.source_diagnostic_scraper
            elif not self.allow_unregistered_sources:
                return _failed_source_test(
                    f"no scraper adapter is registered for {source_kind}"
                )
            else:
                scraper = self.source_test_scraper
        listings = await scraper.fetch_listings(
            ScrapeRequest(
                source_id=0,
                source_name="source test",
                source_kind=source_kind,
                base_url=url,
                watch_id=0,
                included_keywords=[],
                excluded_keywords=[],
                criteria_version=1,
            )
        )
        custom_result = _build_adapter_source_test_result(scraper, listings)
        if custom_result is not None:
            return custom_result

        warnings = []
        if any(listing.price_amount is None for listing in listings):
            warnings.append("some listings are missing price")
        if any(listing.mileage_value is None for listing in listings):
            warnings.append("some listings are missing mileage")

        return SourceTestResult(
            url_accepted=True,
            listings_found=len(listings),
            title_parsing_worked=bool(listings)
            and all(bool(listing.title) for listing in listings),
            link_parsing_worked=bool(listings)
            and all(bool(listing.url) for listing in listings),
            price_parsing_worked=any(
                listing.price_amount is not None for listing in listings
            ),
            mileage_parsing_worked=any(
                listing.mileage_value is not None for listing in listings
            ),
            warnings=warnings,
            errors=[],
        )

    def _record_source_test(
        self,
        session: Session,
        user_id: int,
        url: str,
        source_test: SourceTestResult,
        source_id: int | None = None,
    ) -> None:
        """Persist a source test attempt."""

        status = "failed"
        if not source_test.errors:
            status = "warning" if source_test.warnings else "passed"
        SourceTestAttemptRepository(session).create_attempt(
            user_id=user_id,
            source_id=source_id,
            url=url,
            status=status,
            notes=source_test.warnings,
            detected_links=[],
            error_message="; ".join(source_test.errors) or None,
        )

    def _source_summary(self, source: Source) -> SourceSummary:
        """Create an interface-safe source summary."""

        return SourceSummary(
            source_id=source.id,
            name=source.name,
            kind=source.kind,
            base_url=source.base_url,
        )


def _normalize_source_name(name: str | None, url: str) -> _SourceNameInput:
    """Normalize a source name."""

    explicit_name = (name or "").strip()
    normalized_name = explicit_name or _source_name_for_url(url)
    if not normalized_name:
        raise SourceValidationError("source name is required")
    return _SourceNameInput(name=normalized_name, is_generated=not explicit_name)


def _unique_generated_source_name(
    source_repository: SourceRepository,
    owner_user_id: int,
    base_name: str,
    url: str,
    source_kind: str,
) -> str:
    """Return a generated source name that does not collide with another URL."""

    existing_source = source_repository.get_by_owner_and_name(owner_user_id, base_name)
    if existing_source is None or (
        existing_source.kind == source_kind and existing_source.base_url == url
    ):
        return base_name

    suffix = 2
    while True:
        candidate_name = f"{base_name} {suffix}"
        existing_source = source_repository.get_by_owner_and_name(
            owner_user_id,
            candidate_name,
        )
        if existing_source is None or (
            existing_source.kind == source_kind and existing_source.base_url == url
        ):
            return candidate_name
        suffix += 1


def _source_name_for_url(url: str) -> str:
    """Build a default source name from a URL domain."""

    parsed_url = urlparse(url)
    host = parsed_url.netloc.casefold().split("@")[-1].split(":")[0]
    if host.startswith("www."):
        host = host.removeprefix("www.")
    if not host:
        return ""
    return host.split(".")[0]


def _failed_source_test(error_message: str) -> SourceTestResult:
    """Build a failed source test result."""

    return SourceTestResult(
        url_accepted=False,
        listings_found=0,
        title_parsing_worked=False,
        link_parsing_worked=False,
        price_parsing_worked=False,
        mileage_parsing_worked=False,
        warnings=[],
        errors=[error_message],
    )


def _build_adapter_source_test_result(
    scraper: ScraperAdapter,
    listings: list[ListingCandidate],
) -> SourceTestResult | None:
    """Build a source-test result using adapter-specific parse state when available."""

    builder = getattr(scraper, "build_source_test_result", None)
    if builder is None or not callable(builder):
        return None
    result: Any = builder(listings)
    if isinstance(result, SourceTestResult):
        return result
    return None


def _source_kind_for_url(url: str) -> str:
    """Infer source kind for known adapters."""

    parsed_url = urlparse(url)
    host = parsed_url.netloc.casefold()
    if host.endswith("autotempest.com"):
        return "autotempest"
    if host.endswith("cars-on-line.com"):
        return "cars_on_line"
    if host.endswith("corvette-mag.com"):
        return "corvette_magazine"
    if host.endswith("vettefinders.com"):
        return "vettefinders"
    return "custom_website"
