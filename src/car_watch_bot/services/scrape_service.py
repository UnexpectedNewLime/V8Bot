"""Scrape service for mock-only scheduled collection."""

from decimal import Decimal
from logging import getLogger

from car_watch_bot.core.conversions import convert_usd_to_aud, miles_to_kilometres
from car_watch_bot.core.models import ListingCandidate
from car_watch_bot.core.scoring import score_listing
from car_watch_bot.db.models import Source, Watch
from car_watch_bot.db.repositories import (
    ListingRepository,
    ScrapeAttemptRepository,
    SourceRepository,
    WatchRepository,
)
from car_watch_bot.scrapers.base import ScraperAdapter, ScrapeRequest


logger = getLogger(__name__)


class ScrapeService:
    """Business operations for scheduled scrape collection."""

    def __init__(
        self,
        watch_repository: WatchRepository,
        source_repository: SourceRepository,
        listing_repository: ListingRepository,
        scrape_attempt_repository: ScrapeAttemptRepository,
        scraper_adapters: dict[str, ScraperAdapter],
        usd_to_aud_rate: Decimal,
    ) -> None:
        self.watch_repository = watch_repository
        self.source_repository = source_repository
        self.listing_repository = listing_repository
        self.scrape_attempt_repository = scrape_attempt_repository
        self.scraper_adapters = scraper_adapters
        self.usd_to_aud_rate = usd_to_aud_rate

    async def run_once(self) -> int:
        """Run one mock scrape cycle and return created listing count."""

        created_count = 0
        for watch in self.watch_repository.list_all_active():
            for source in self.source_repository.list_sources_for_watch(watch.id):
                adapter = self.scraper_adapters.get(source.kind)
                if adapter is None:
                    continue
                created_count += await self.scrape_watch_source(watch, source, adapter)
        return created_count

    async def scrape_watch_source(
        self,
        watch: Watch,
        source: Source,
        adapter: ScraperAdapter,
    ) -> int:
        """Scrape one source for one watch."""

        request = ScrapeRequest(
            source_id=source.id,
            source_name=source.name,
            source_kind=source.kind,
            base_url=source.base_url,
            watch_id=watch.id,
            included_keywords=watch.included_keywords,
            excluded_keywords=watch.excluded_keywords,
            criteria_version=watch.criteria_version,
        )
        try:
            candidates = await adapter.fetch_listings(request)
        except Exception as exc:
            logger.warning("scrape failed", extra={"watch_id": watch.id, "source_id": source.id})
            self.scrape_attempt_repository.create_attempt(
                watch_id=watch.id,
                source_id=source.id,
                status="failed",
                adapter_kind=request.source_kind,
                error_message=str(exc),
            )
            return 0

        matched_count = 0
        created_count = 0
        for candidate in candidates:
            score_result = score_listing(
                candidate,
                car_query=watch.query,
                keywords=watch.included_keywords,
                excluded_keywords=watch.excluded_keywords,
            )
            if not score_result.is_match:
                existing_listing = self.listing_repository.find_existing_listing(
                    source_id=source.id,
                    listing=candidate,
                )
                if existing_listing is not None:
                    converted_price = self._converted_price(
                        candidate,
                        watch.preferred_currency,
                    )
                    converted_mileage = self._converted_mileage(
                        candidate,
                        watch.distance_unit,
                    )
                    self.listing_repository.update_listing(
                        existing_listing,
                        candidate,
                        score_result,
                        converted_price,
                        watch.preferred_currency,
                        converted_mileage,
                        watch.distance_unit,
                    )
                    self.listing_repository.exclude_listing_for_watch(
                        watch,
                        existing_listing,
                    )
                continue

            matched_count += 1
            converted_price = self._converted_price(candidate, watch.preferred_currency)
            converted_mileage = self._converted_mileage(candidate, watch.distance_unit)
            listing, was_created = self.listing_repository.insert_listing_if_new(
                source_id=source.id,
                listing=candidate,
                score_result=score_result,
                converted_price_amount=converted_price,
                converted_price_currency=watch.preferred_currency,
                converted_mileage_value=converted_mileage,
                converted_mileage_unit=watch.distance_unit,
            )
            self.listing_repository.add_listing_to_watch(watch, listing)
            if was_created:
                created_count += 1

        self.scrape_attempt_repository.create_attempt(
            watch_id=watch.id,
            source_id=source.id,
            status="success",
            adapter_kind=request.source_kind,
            listings_seen=len(candidates),
            listings_matched=matched_count,
            listings_created=created_count,
        )
        return created_count

    def _converted_price(
        self,
        listing: ListingCandidate,
        preferred_currency: str,
    ) -> Decimal | None:
        """Convert listing price into the watch currency."""

        if listing.price_amount is None:
            return None
        if listing.price_currency == preferred_currency:
            return listing.price_amount
        if listing.price_currency == "USD" and preferred_currency == "AUD":
            return convert_usd_to_aud(listing.price_amount, self.usd_to_aud_rate)
        return None

    def _converted_mileage(
        self,
        listing: ListingCandidate,
        distance_unit: str,
    ) -> int | None:
        """Convert listing mileage into the watch distance unit."""

        if listing.mileage_value is None:
            return None
        if listing.mileage_unit == distance_unit:
            return listing.mileage_value
        if listing.mileage_unit == "mi" and distance_unit == "km":
            return miles_to_kilometres(listing.mileage_value)
        return None
