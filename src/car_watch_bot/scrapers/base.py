"""Base scraper interface."""

from dataclasses import dataclass
from typing import Protocol

from car_watch_bot.core.models import ListingCandidate


@dataclass(frozen=True)
class ScrapeRequest:
    """Input for a scraper adapter."""

    source_id: int
    source_name: str
    source_kind: str
    base_url: str | None
    watch_id: int
    included_keywords: list[str]
    excluded_keywords: list[str]
    criteria_version: int


class ScraperAdapter(Protocol):
    """Interface every scheduled scraper adapter must implement."""

    @property
    def source_kind(self) -> str:
        """Return the source kind handled by the adapter."""
        ...

    async def fetch_listings(self, request: ScrapeRequest) -> list[ListingCandidate]:
        """Fetch listing candidates from the source."""
        ...
