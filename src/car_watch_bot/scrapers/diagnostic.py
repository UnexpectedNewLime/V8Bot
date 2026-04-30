"""Polite diagnostic fetch for unsupported source URLs."""

import logging
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import Tag

from car_watch_bot.core.models import ListingCandidate, SourceTestResult
from car_watch_bot.scrapers.base import ScrapeRequest
from car_watch_bot.scrapers.static_html import (
    StaticHtmlScraper,
    clean_text,
    extract_mileage,
    extract_price,
    soup_from_html,
)


logger = logging.getLogger(__name__)


class DiagnosticScraper(StaticHtmlScraper):
    """Best-effort diagnostic scraper for unsupported domains."""

    source_label = "diagnostic source"

    @property
    def source_kind(self) -> str:
        """Return the source kind handled by this adapter."""

        return "diagnostic"

    async def fetch_listings(self, request: ScrapeRequest) -> list[ListingCandidate]:
        """Fetch one unsupported URL and collect page-level diagnostics."""

        self.last_warnings = []
        self.last_errors = []
        if not request.base_url:
            self.last_errors.append("diagnostic source requires a base_url")
            return []
        domain = _domain_for_url(request.base_url)
        self.last_warnings.append(
            f"domain not supported for scheduled scraping: {domain}"
        )
        try:
            html = await self._fetch_html(request.base_url)
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            self.last_errors.append(f"polite fetch failed with HTTP {status_code}")
            return []
        except httpx.HTTPError as exc:
            return self._handle_fetch_error(exc, request.source_id, logger)
        except Exception as exc:
            return self._handle_unexpected_fetch_error(exc, logger)
        return self.parse_html(html, request.base_url, request.source_name)

    def parse_html(
        self,
        html: str,
        base_url: str,
        source_name: str = "Diagnostic",
    ) -> list[ListingCandidate]:
        """Parse page-level diagnostics into rough candidates."""

        soup = soup_from_html(html)
        title = _page_title(soup)
        if title:
            self.last_warnings.append(f"page title: {title}")
        links = _diagnostic_links(soup, base_url)
        if not links:
            self.last_warnings.append("polite fetch succeeded, but no links were found")
            return []
        self.last_warnings.append(f"links found: {len(links)}")
        candidates = [
            _link_to_candidate(link, source_name)
            for link in links[:5]
        ]
        candidate_count = len(candidates)
        if candidate_count:
            self.last_warnings.append(
                f"sampled {candidate_count} links; these are not validated listings"
            )
        return candidates

    def build_source_test_result(
        self,
        listings: list[ListingCandidate],
    ) -> SourceTestResult:
        """Build an unsupported-domain source test result."""

        return SourceTestResult(
            url_accepted=False,
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
            warnings=list(self.last_warnings),
            errors=list(self.last_errors),
        )


def _page_title(soup) -> str | None:
    """Return a cleaned page title."""

    if soup.title is None:
        return None
    title = clean_text(soup.title.get_text(" ", strip=True))
    return title or None


def _diagnostic_links(soup, base_url: str) -> list[tuple[str, str, str]]:
    """Return unique visible links with nearby text."""

    links: list[tuple[str, str, str]] = []
    seen_urls: set[str] = set()
    for anchor in soup.select("a[href]"):
        if not isinstance(anchor, Tag):
            continue
        href = str(anchor.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        url = urljoin(base_url, href)
        parsed_url = urlparse(url)
        if parsed_url.scheme not in {"http", "https"} or url in seen_urls:
            continue
        text = clean_text(anchor.get_text(" ", strip=True))
        nearby_text = clean_text(anchor.parent.get_text(" ", strip=True)) if anchor.parent else text
        links.append((text or url, url, nearby_text))
        seen_urls.add(url)
    return links


def _link_to_candidate(
    link: tuple[str, str, str],
    source_name: str,
) -> ListingCandidate:
    """Convert a diagnostic link into a rough candidate."""

    title, url, raw_text = link
    price_amount = extract_price(raw_text)
    mileage_value = extract_mileage(raw_text)
    return ListingCandidate(
        title=title,
        url=url,
        description=raw_text or None,
        price_amount=price_amount,
        price_currency="USD" if price_amount is not None else None,
        mileage_value=mileage_value,
        mileage_unit="mi" if mileage_value is not None else None,
        source_name=source_name,
    )


def _domain_for_url(url: str) -> str:
    """Return a user-facing URL domain."""

    return urlparse(url).netloc.casefold() or "unknown domain"
