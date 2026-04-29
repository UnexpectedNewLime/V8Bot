"""Core domain models shared across services."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal


@dataclass(frozen=True)
class ListingCandidate:
    """Normalized listing candidate passed across scraper boundaries."""

    title: str
    url: str
    external_id: str | None = None
    description: str | None = None
    price_amount: Decimal | None = None
    price_currency: str | None = None
    mileage_value: int | None = None
    mileage_unit: Literal["km", "mi"] | None = None
    location_text: str | None = None
    source_name: str | None = None
    listed_at: datetime | None = None
    raw_payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class ScoreResult:
    """Deterministic listing match score and reasons."""

    score: int
    is_match: bool
    reasons: list[str]


@dataclass(frozen=True)
class ConvertedListing:
    """Listing values after user-preference conversions."""

    original_price_amount: Decimal | None
    original_price_currency: str | None
    converted_price_amount: Decimal | None
    converted_price_currency: str | None
    original_mileage_value: int | None
    original_mileage_unit: str | None
    converted_mileage_value: int | None
    converted_mileage_unit: str | None


@dataclass(frozen=True)
class SourceTestResult:
    """Structured result for a mock-only source test."""

    url_accepted: bool
    listings_found: int
    title_parsing_worked: bool
    link_parsing_worked: bool
    price_parsing_worked: bool
    mileage_parsing_worked: bool
    warnings: list[str]
    errors: list[str]


@dataclass(frozen=True)
class DigestListing:
    """Listing data formatted for a scheduled digest."""

    listing_id: int
    title: str
    source_name: str
    original_price: str
    converted_price: str
    original_mileage: str
    converted_mileage: str
    score_reasons: list[str]
    url: str


@dataclass(frozen=True)
class DigestPayload:
    """Digest data ready for presentation by an interface layer."""

    watch_name: str
    watch_query: str
    listing_count: int
    listings: list[DigestListing]


@dataclass(frozen=True)
class ScrapeNowResult:
    """Result of a user-triggered scrape."""

    watch_id: int
    sources_seen: int
    sources_scraped: int
    sources_skipped: int
    listings_created: int
    pending_listings: int
    warnings: list[str]
    new_listing_ids: list[int]
