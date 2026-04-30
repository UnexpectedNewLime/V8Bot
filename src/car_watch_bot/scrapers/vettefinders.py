"""VetteFinders scraper adapter."""

import logging
import re
from urllib.parse import urljoin

import httpx
from bs4 import Tag

from car_watch_bot.core.models import ListingCandidate
from car_watch_bot.scrapers.base import ScrapeRequest
from car_watch_bot.scrapers.static_html import (
    StaticHtmlScraper,
    clean_text,
    extract_mileage,
    extract_price,
    query_value,
    raw_payload,
    soup_from_html,
)


logger = logging.getLogger(__name__)
STATE_PATTERN = re.compile(r"\bState:\s*([A-Z]{2})\b")
ID_PATTERN = re.compile(r"(?:[?&]|/)id=(\d+)\b")


class VetteFindersScraper(StaticHtmlScraper):
    """Scraper adapter for VetteFinders static C5 summary pages."""

    source_label = "vettefinders"

    @property
    def source_kind(self) -> str:
        """Return the source kind handled by this adapter."""

        return "vettefinders"

    async def fetch_listings(self, request: ScrapeRequest) -> list[ListingCandidate]:
        """Fetch and parse VetteFinders listing candidates."""

        self.last_warnings = []
        self.last_errors = []
        if not request.base_url:
            self.last_errors.append("VetteFinders source requires a base_url")
            return []
        try:
            html = await self._fetch_html(request.base_url)
        except httpx.HTTPError as exc:
            return self._handle_fetch_error(exc, request.source_id, logger)
        except Exception as exc:
            return self._handle_unexpected_fetch_error(exc, logger)
        return self.parse_html(html, request.base_url, request.source_name)

    def parse_html(
        self,
        html: str,
        base_url: str,
        source_name: str = "VetteFinders",
    ) -> list[ListingCandidate]:
        """Parse VetteFinders static HTML into listing candidates."""

        self.last_warnings = []
        self.last_errors = []
        soup = soup_from_html(html)
        candidates = [
            candidate
            for card in soup.select("div.row.content-padding")
            if (candidate := self._parse_card(card, base_url, source_name)) is not None
        ]
        if not candidates:
            self.last_warnings.append("no VetteFinders listing rows found")
        return candidates

    def _parse_card(
        self,
        card: Tag,
        base_url: str,
        source_name: str,
    ) -> ListingCandidate | None:
        """Parse one VetteFinders listing row."""

        link = card.select_one('a[href*="CarDetail"][href*="id="]')
        if not isinstance(link, Tag):
            return None
        href = str(link.get("href") or "")
        title = clean_text(link.get_text(" ", strip=True))
        if not href or not title:
            return None
        raw_text = clean_text(card.get_text(" ", strip=True))
        price_amount = extract_price(raw_text)
        mileage_value = extract_mileage(raw_text)
        location_text = _state_text(raw_text)
        url = urljoin(base_url, href)
        return ListingCandidate(
            external_id=_external_id(url),
            title=title,
            url=url,
            description=raw_text,
            price_amount=price_amount,
            price_currency="USD" if price_amount is not None else None,
            mileage_value=mileage_value,
            mileage_unit="mi" if mileage_value is not None else None,
            location_text=location_text,
            source_name=source_name,
            raw_payload=raw_payload(
                candidate_type="vettefinders_listing",
                raw_text=raw_text,
                price_amount=price_amount,
                mileage_value=mileage_value,
                extra={"location_text": location_text},
            ),
        )


def _state_text(raw_text: str) -> str | None:
    """Extract state text from a VetteFinders row."""

    match = STATE_PATTERN.search(raw_text)
    if match is None:
        return None
    return match.group(1)


def _external_id(url: str) -> str | None:
    """Extract VetteFinders id from query or ColdFusion-style path."""

    return query_value(url, "id") or _path_id(url)


def _path_id(url: str) -> str | None:
    """Extract id from legacy paths without a query marker."""

    match = ID_PATTERN.search(url)
    if match is None:
        return None
    return match.group(1)
