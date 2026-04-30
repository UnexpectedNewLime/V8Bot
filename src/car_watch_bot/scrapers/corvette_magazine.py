"""Corvette Magazine classifieds scraper adapter."""

import logging
from decimal import Decimal
from urllib.parse import urljoin

import httpx
from bs4 import Tag

from car_watch_bot.core.models import ListingCandidate
from car_watch_bot.scrapers.base import ScrapeRequest
from car_watch_bot.scrapers.static_html import (
    StaticHtmlScraper,
    clean_text,
    decimal_price,
    extract_mileage,
    extract_price,
    path_external_id,
    raw_payload,
    soup_from_html,
)


logger = logging.getLogger(__name__)


class CorvetteMagazineScraper(StaticHtmlScraper):
    """Scraper adapter for Corvette Magazine static classifieds."""

    source_label = "corvette_magazine"

    @property
    def source_kind(self) -> str:
        """Return the source kind handled by this adapter."""

        return "corvette_magazine"

    async def fetch_listings(self, request: ScrapeRequest) -> list[ListingCandidate]:
        """Fetch and parse Corvette Magazine listing candidates."""

        self.last_warnings = []
        self.last_errors = []
        if not request.base_url:
            self.last_errors.append("Corvette Magazine source requires a base_url")
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
        source_name: str = "Corvette Magazine",
    ) -> list[ListingCandidate]:
        """Parse Corvette Magazine static HTML into listing candidates."""

        self.last_warnings = []
        self.last_errors = []
        soup = soup_from_html(html)
        candidates = [
            candidate
            for card in soup.select('li[itemtype="https://schema.org/Car"]')
            if (candidate := self._parse_card(card, base_url, source_name)) is not None
        ]
        if not candidates:
            self.last_warnings.append("no Corvette Magazine classified cards found")
        return candidates

    def _parse_card(
        self,
        card: Tag,
        base_url: str,
        source_name: str,
    ) -> ListingCandidate | None:
        """Parse one Corvette Magazine classified card."""

        link = card.select_one('a[itemprop="url"][href]')
        if not isinstance(link, Tag):
            return None
        href = str(link.get("href") or "")
        title = _title_text(card, link)
        if not href or not title:
            return None
        raw_text = clean_text(card.get_text(" ", strip=True))
        price_amount = _price_amount(card, raw_text)
        mileage_value = extract_mileage(raw_text)
        location_text = _selector_text(card, ".location")
        url = urljoin(base_url, href)
        return ListingCandidate(
            external_id=path_external_id(url),
            title=title,
            url=url,
            description=_selector_text(card, ".description") or raw_text,
            price_amount=price_amount,
            price_currency="USD" if price_amount is not None else None,
            mileage_value=mileage_value,
            mileage_unit="mi" if mileage_value is not None else None,
            location_text=location_text,
            source_name=source_name,
            raw_payload=raw_payload(
                candidate_type="corvette_magazine_classified",
                raw_text=raw_text,
                price_amount=price_amount,
                mileage_value=mileage_value,
                extra={
                    "location_text": location_text,
                    "listed_date": _selector_text(card, ".date"),
                },
            ),
        )


def _title_text(card: Tag, link: Tag) -> str:
    """Extract title text from a classified card."""

    title = _selector_text(card, ".title")
    if title:
        return title
    return clean_text(str(link.get("title") or link.get_text(" ", strip=True)))


def _price_amount(card: Tag, raw_text: str) -> Decimal | None:
    """Extract a classified price from metadata or visible text."""

    price = card.select_one('[itemprop="price"]')
    if isinstance(price, Tag):
        amount = decimal_price(str(price.get("content") or ""))
        if amount is not None:
            return amount
    return extract_price(raw_text)


def _selector_text(card: Tag, selector: str) -> str | None:
    """Extract cleaned text from a selector."""

    element = card.select_one(selector)
    if element is None:
        return None
    text = clean_text(element.get_text(" ", strip=True))
    return text or None
