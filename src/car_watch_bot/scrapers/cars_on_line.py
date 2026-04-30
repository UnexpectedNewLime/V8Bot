"""Cars On Line scraper adapter."""

import logging
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
    raw_payload,
    soup_from_html,
)


logger = logging.getLogger(__name__)


class CarsOnLineScraper(StaticHtmlScraper):
    """Scraper adapter for Cars On Line static listing cards."""

    source_label = "cars_on_line"

    @property
    def source_kind(self) -> str:
        """Return the source kind handled by this adapter."""

        return "cars_on_line"

    async def fetch_listings(self, request: ScrapeRequest) -> list[ListingCandidate]:
        """Fetch and parse Cars On Line listing candidates."""

        self.last_warnings = []
        self.last_errors = []
        if not request.base_url:
            self.last_errors.append("Cars On Line source requires a base_url")
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
        source_name: str = "Cars On Line",
    ) -> list[ListingCandidate]:
        """Parse Cars On Line static HTML into listing candidates."""

        self.last_warnings = []
        self.last_errors = []
        soup = soup_from_html(html)
        candidates = [
            candidate
            for card in soup.select("li.job_listing")
            if (candidate := self._parse_card(card, base_url, source_name)) is not None
        ]
        if not candidates:
            self.last_warnings.append("no Cars On Line listing cards found")
        return candidates

    def _parse_card(
        self,
        card: Tag,
        base_url: str,
        source_name: str,
    ) -> ListingCandidate | None:
        """Parse one Cars On Line listing card."""

        link = card.select_one("a.job_listing-clickbox[href]")
        if not isinstance(link, Tag):
            return None
        href = str(link.get("href") or "")
        if not href:
            return None
        title = _card_title(card)
        if not title:
            return None
        raw_text = clean_text(card.get_text(" ", strip=True))
        price_amount = extract_price(raw_text)
        mileage_value = extract_mileage(raw_text)
        external_id = str(link.get("data-vid") or "") or _listing_id(card)
        location_text = _location_text(card)
        return ListingCandidate(
            external_id=external_id,
            title=title,
            url=urljoin(base_url, href),
            description=raw_text,
            price_amount=price_amount,
            price_currency="USD" if price_amount is not None else None,
            mileage_value=mileage_value,
            mileage_unit="mi" if mileage_value is not None else None,
            location_text=location_text,
            source_name=source_name,
            raw_payload=raw_payload(
                candidate_type="cars_on_line_listing",
                raw_text=raw_text,
                price_amount=price_amount,
                mileage_value=mileage_value,
                extra={"location_text": location_text},
            ),
        )


def _card_title(card: Tag) -> str:
    """Build a useful title from year plus card title."""

    year_element = card.select_one(".job_listing-year")
    title_element = card.select_one(".job_listing-title")
    year = (
        clean_text(year_element.get_text(" ", strip=True))
        if year_element is not None
        else ""
    )
    title = (
        clean_text(title_element.get_text(" ", strip=True))
        if title_element is not None
        else ""
    )
    return clean_text(f"{year} {title}")


def _location_text(card: Tag) -> str | None:
    """Extract Cars On Line location text."""

    location = card.select_one(".job_listing-location")
    if location is None:
        return None
    text = clean_text(location.get_text(" ", strip=True)).strip("[]")
    return text or None


def _listing_id(card: Tag) -> str | None:
    """Extract listing id from the card id attribute."""

    card_id = str(card.get("id") or "")
    if card_id.startswith("listing-"):
        return card_id.removeprefix("listing-")
    return None
