"""Service workflows for guided source presets."""

from dataclasses import dataclass

from car_watch_bot.core.models import DigestListing, ScrapeNowResult
from car_watch_bot.core.source_presets import (
    AutoTempestSearchCriteria,
    build_autotempest_keywords,
    build_autotempest_source_name,
    build_autotempest_url,
    build_autotempest_watch_query,
)
from car_watch_bot.services.listing_service import ListingService
from car_watch_bot.services.source_service import SourceAddResult, SourceService
from car_watch_bot.services.watch_service import WatchService, WatchSummary


@dataclass(frozen=True)
class AutoTempestWatchSetupResult:
    """Result returned by an AutoTempest watch preset setup."""

    watch: WatchSummary
    source_url: str
    source_result: SourceAddResult
    scrape_result: ScrapeNowResult | None
    listings: list[DigestListing]


class SourcePresetService:
    """Business workflows for guided source presets."""

    def __init__(
        self,
        watch_service: WatchService,
        source_service: SourceService,
        listing_service: ListingService,
    ) -> None:
        self.watch_service = watch_service
        self.source_service = source_service
        self.listing_service = listing_service

    async def add_autotempest_watch(
        self,
        *,
        discord_user_id: str,
        make: str,
        model: str,
        notify_time: str,
        year_min: int | None = None,
        year_max: int | None = None,
        transmission: str | None = None,
        zip_postcode: str | None = None,
        radius: int | None = None,
        keywords: str | None = None,
        exclude_keywords: str | None = None,
        guild_id: str | None = None,
        channel_id: str | None = None,
        scrape_now: bool = True,
    ) -> AutoTempestWatchSetupResult:
        """Create a watch and attach a generated AutoTempest source."""

        criteria = AutoTempestSearchCriteria(
            make=make,
            model=model,
            year_min=year_min,
            year_max=year_max,
            transmission=transmission,
            zip_postcode=zip_postcode,
            radius=radius,
        )
        source_url = build_autotempest_url(criteria)
        watch = self.watch_service.create_watch(
            discord_user_id=discord_user_id,
            car_query=build_autotempest_watch_query(criteria),
            keywords=build_autotempest_keywords(criteria, keywords),
            exclude_keywords=exclude_keywords or "",
            notify_time=notify_time,
            guild_id=guild_id,
            channel_id=channel_id,
        )
        source_result = await self.source_service.add_source_to_watch(
            discord_user_id=discord_user_id,
            watch_id=watch.watch_id,
            name=build_autotempest_source_name(criteria),
            url=source_url,
        )
        scrape_result: ScrapeNowResult | None = None
        listings: list[DigestListing] = []
        if scrape_now:
            scrape_result = await self.listing_service.scrape_watch_now(
                discord_user_id,
                watch.watch_id,
            )
            listings = self.listing_service.list_watch_listings(
                discord_user_id,
                watch.watch_id,
                listing_ids=scrape_result.new_listing_ids,
            )
        return AutoTempestWatchSetupResult(
            watch=watch,
            source_url=source_url,
            source_result=source_result,
            scrape_result=scrape_result,
            listings=listings,
        )
