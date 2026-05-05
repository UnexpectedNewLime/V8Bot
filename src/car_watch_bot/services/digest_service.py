"""Digest service for formatting persisted listings."""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from car_watch_bot.core.models import DigestListing, DigestPayload
from car_watch_bot.db.models import Listing, Watch
from car_watch_bot.db.repositories import ListingRepository

SOURCE_NAME_BY_DOMAIN = {
    "cars.com": "Cars.com",
    "ebay.com": "eBay",
    "hemmings.com": "Hemmings",
    "truecar.com": "TrueCar",
}
SELLER_FIELD_LABELS = (
    ("dealer_name", "Dealer"),
    ("dealerName", "Dealer"),
    ("dealer", "Dealer"),
    ("seller_name", "Seller"),
    ("sellerName", "Seller"),
    ("seller", "Seller"),
    ("seller_type", "Seller type"),
    ("sellerType", "Seller type"),
)
IMAGE_URL_KEYS = (
    "thumbnail_url",
    "thumbnailUrl",
    "image_url",
    "imageUrl",
    "primary_image_url",
    "primaryImageUrl",
    "photo_url",
    "photoUrl",
)
IMAGE_COLLECTION_KEYS = ("images", "image_urls", "imageUrls", "photos", "photoUrls")
FIRST_SEEN_PRICE_AMOUNT_KEY = "v8bot_first_seen_price_amount"
FIRST_SEEN_PRICE_CURRENCY_KEY = "v8bot_first_seen_price_currency"
PREVIOUS_PRICE_AMOUNT_KEY = "v8bot_previous_price_amount"
PREVIOUS_PRICE_CURRENCY_KEY = "v8bot_previous_price_currency"
SYDNEY_TIMEZONE = ZoneInfo("Australia/Sydney")


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
        """Build a listing payload for visible watch listings."""

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
        raw_payload = self._raw_payload(listing)
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
            location=self._clean_text(listing.location_text),
            first_seen=self._format_timestamp(listing.first_seen_at),
            last_seen=self._format_timestamp(listing.last_seen_at),
            seller_info=self._seller_info(raw_payload),
            image_url=self._image_url(raw_payload),
            price_change=self._price_change(listing, raw_payload),
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

    def _raw_payload(self, listing: Listing) -> dict[str, Any]:
        """Return listing raw payload when it is a JSON object."""

        raw_payload = listing.raw_payload or {}
        return raw_payload if isinstance(raw_payload, dict) else {}

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

    def _format_timestamp(self, value: datetime | None) -> str | None:
        """Format stored UTC-ish timestamps in Sydney local time."""

        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        value = value.astimezone(SYDNEY_TIMEZONE)
        return value.strftime("%Y-%m-%d %H:%M %Z")

    def _seller_info(self, raw_payload: dict[str, Any]) -> str | None:
        """Extract concise seller/dealer context from scraper metadata."""

        lines: list[str] = []
        seen_values: set[str] = set()
        for key, label in SELLER_FIELD_LABELS:
            value = self._raw_text_value(raw_payload.get(key))
            if value is None or value in seen_values:
                continue
            lines.append(f"{label}: {value}")
            seen_values.add(value)
        return "\n".join(lines[:3]) or None

    def _image_url(self, raw_payload: dict[str, Any]) -> str | None:
        """Return the first usable HTTP image URL from scraper metadata."""

        for key in IMAGE_URL_KEYS:
            image_url = self._raw_url(raw_payload.get(key))
            if image_url is not None:
                return image_url
        for key in IMAGE_COLLECTION_KEYS:
            collection = raw_payload.get(key)
            if not isinstance(collection, list):
                continue
            for value in collection:
                image_url = self._raw_url(value)
                if image_url is not None:
                    return image_url
        return None

    def _price_change(self, listing: Listing, raw_payload: dict[str, Any]) -> str | None:
        """Format price-change context when stored history supports it."""

        current_amount = listing.price_amount
        current_currency = listing.price_currency
        if current_amount is None or current_currency is None:
            return None

        historical_price = self._stored_price(
            raw_payload,
            FIRST_SEEN_PRICE_AMOUNT_KEY,
            FIRST_SEEN_PRICE_CURRENCY_KEY,
        )
        if historical_price is None:
            historical_price = self._stored_price(
                raw_payload,
                PREVIOUS_PRICE_AMOUNT_KEY,
                PREVIOUS_PRICE_CURRENCY_KEY,
            )
        if historical_price is None:
            return None

        historical_amount, historical_currency = historical_price
        if historical_amount == current_amount and historical_currency == current_currency:
            return None
        return self._format_price_delta(
            historical_amount,
            historical_currency,
            current_amount,
            current_currency,
        )

    def _format_price_delta(
        self,
        historical_amount: Decimal,
        historical_currency: str,
        current_amount: Decimal,
        current_currency: str,
    ) -> str:
        """Format a known historical/current price comparison."""

        historical_price = self._format_price(historical_amount, historical_currency)
        current_price = self._format_price(current_amount, current_currency)
        if historical_currency != current_currency:
            return f"Changed from {historical_price} to {current_price}"
        delta = current_amount - historical_amount
        direction = "Up" if delta > 0 else "Down"
        return (
            f"{direction} {historical_currency} {abs(delta):,.0f} "
            f"from {historical_price} to {current_price}"
        )

    def _stored_price(
        self,
        raw_payload: dict[str, Any],
        amount_key: str,
        currency_key: str,
    ) -> tuple[Decimal, str] | None:
        """Read a stored price snapshot from raw metadata."""

        amount = self._decimal_value(raw_payload.get(amount_key))
        currency = self._clean_text(raw_payload.get(currency_key))
        if amount is None or currency is None:
            return None
        return amount, currency

    def _raw_url(self, value: object) -> str | None:
        """Extract a usable HTTP URL from common raw payload shapes."""

        if isinstance(value, dict):
            for key in ("url", "href", *IMAGE_URL_KEYS):
                url = self._raw_url(value.get(key))
                if url is not None:
                    return url
            return None
        text = self._clean_text(value)
        if text is None:
            return None
        if not text.startswith(("http://", "https://")):
            return None
        return text

    def _raw_text_value(self, value: object) -> str | None:
        """Extract display text from common raw payload scalar or object shapes."""

        if isinstance(value, dict):
            for key in ("name", "display_name", "displayName", "type"):
                text = self._clean_text(value.get(key))
                if text is not None:
                    return text
            return None
        return self._clean_text(value)

    def _clean_text(self, value: object) -> str | None:
        """Normalize optional text for digest output."""

        if not isinstance(value, str):
            return None
        text = value.strip()
        return text or None

    def _decimal_value(self, value: object) -> Decimal | None:
        """Normalize a stored decimal-like JSON value."""

        if value is None:
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
