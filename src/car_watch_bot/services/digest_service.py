"""Digest service for formatting persisted listings."""

from decimal import Decimal
from urllib.parse import urlparse

from car_watch_bot.core.models import DigestListing, DigestPayload
from car_watch_bot.db.models import Listing, Watch
from car_watch_bot.db.repositories import ListingRepository

SOURCE_NAME_BY_DOMAIN = {
    "cars.com": "Cars.com",
    "ebay.com": "eBay",
    "hemmings.com": "Hemmings",
    "truecar.com": "TrueCar",
}


class DigestService:
    """Business operations for digest selection and state changes."""

    def __init__(self, listing_repository: ListingRepository) -> None:
        self.listing_repository = listing_repository

    def build_digest(self, watch: Watch) -> DigestPayload | None:
        """Build a digest payload from persisted pending listings."""

        listings = self.listing_repository.list_unnotified_for_watch(watch.id)
        return self._build_digest_from_listings(watch, listings)

    def build_digest_for_listing_ids(
        self,
        watch: Watch,
        listing_ids: list[int],
    ) -> DigestPayload | None:
        """Build a digest payload for selected pending listing IDs."""

        listings = self.listing_repository.list_unnotified_for_watch_listing_ids(
            watch.id,
            listing_ids,
        )
        return self._build_digest_from_listings(watch, listings)

    def build_listing_history(self, watch: Watch) -> DigestPayload | None:
        """Build a listing payload for all non-excluded watch listings."""

        listings = self.listing_repository.list_visible_for_watch(watch.id)
        return self._build_digest_from_listings(watch, listings)

    def _build_digest_from_listings(
        self,
        watch: Watch,
        listings: list[Listing],
    ) -> DigestPayload | None:
        """Build a digest payload from listing rows."""

        if not listings:
            return None
        digest_listings = [self._format_listing(listing) for listing in listings]
        return DigestPayload(
            watch_name=watch.name,
            watch_query=watch.query,
            listing_count=len(digest_listings),
            listings=digest_listings,
        )

    def mark_digest_sent(self, watch_id: int, listing_ids: list[int]) -> None:
        """Mark digest listings as notified after successful send."""

        self.listing_repository.mark_listings_as_notified(watch_id, listing_ids)

    def _format_listing(self, listing: Listing) -> DigestListing:
        """Format one listing for a digest."""

        source_name = self._listing_source_name(listing)
        return DigestListing(
            listing_id=listing.id,
            title=listing.title,
            source_name=source_name,
            original_price=self._format_price(listing.price_amount, listing.price_currency),
            converted_price=self._format_price(
                listing.converted_price_amount,
                listing.converted_price_currency,
            ),
            original_mileage=self._format_mileage(listing.mileage_value, listing.mileage_unit),
            converted_mileage=self._format_mileage(
                listing.converted_mileage_value,
                listing.converted_mileage_unit,
            ),
            score_reasons=listing.score_reasons,
            url=listing.url,
        )

    def _listing_source_name(self, listing: Listing) -> str:
        """Return the display source for a listing."""

        raw_payload = listing.raw_payload or {}
        if isinstance(raw_payload, dict):
            source_name = raw_payload.get("listing_source_name")
            if isinstance(source_name, str) and source_name.strip():
                return source_name.strip()
        domain_source_name = self._source_name_from_url(listing.url)
        if domain_source_name is not None:
            return domain_source_name
        if listing.source is not None:
            return listing.source.name
        return "Unknown source"

    def _source_name_from_url(self, url: str) -> str | None:
        """Infer common marketplace names for older persisted listings."""

        hostname = urlparse(url).hostname or ""
        hostname = hostname.removeprefix("www.")
        for domain, source_name in SOURCE_NAME_BY_DOMAIN.items():
            if hostname == domain or hostname.endswith(f".{domain}"):
                return source_name
        return None

    def _format_price(self, amount: Decimal | None, currency: str | None) -> str:
        """Format a price for digest output."""

        if amount is None or currency is None:
            return "not listed"
        return f"{currency} {amount:,.0f}"

    def _format_mileage(self, value: int | None, unit: str | None) -> str:
        """Format mileage for digest output."""

        if value is None or unit is None:
            return "not listed"
        return f"{value:,} {unit}"
