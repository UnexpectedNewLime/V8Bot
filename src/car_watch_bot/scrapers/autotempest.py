"""AutoTempest scraper adapter."""

import asyncio
import hashlib
import json
import logging
import re
import time
from decimal import Decimal
from typing import Any
from urllib.parse import quote, unquote, urldefrag, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, Tag

from car_watch_bot.core.models import ListingCandidate, SourceTestResult
from car_watch_bot.scrapers.base import ScrapeRequest


logger = logging.getLogger(__name__)

PRICE_PATTERN = re.compile(r"\$\s*([\d,]+(?:\.\d{2})?)")
MILEAGE_PATTERN = re.compile(r"([\d,]+)\s*(?:mi|mile|miles)\b", re.IGNORECASE)
SEARCH_PARAMS_PATTERN = re.compile(r"searchParams\s*=\s*(\{.*?\});", re.DOTALL)
QUEUE_TOKEN_SECRET = "d8007486d73c168684860aae427ea1f9d74e502b06d94609691f5f4f2704a07f"
QUEUE_SOURCE_CODES = {"te", "hem", "cs", "cv", "cm", "eb", "ot"}
QUEUE_DEDUPE_SOURCE_CODES = ["te", "hem", "cs", "cv", "cm", "eb", "ot", "st", "fbm"]
QUERY_SAFE_CHARS = "-_.!~*'()"


class AutoTempestScraper:
    """Scraper adapter for AutoTempest static HTML."""

    def __init__(
        self,
        user_agent: str,
        timeout_seconds: float = 10.0,
        min_interval_seconds: float = 2.0,
        capture_comparison_links: bool = False,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds
        self.min_interval_seconds = min_interval_seconds
        self.capture_comparison_links = capture_comparison_links
        self.http_client = http_client
        self.last_request_at: float | None = None
        self.last_warnings: list[str] = []
        self.last_errors: list[str] = []

    @property
    def source_kind(self) -> str:
        """Return the source kind handled by this adapter."""

        return "autotempest"

    async def fetch_listings(self, request: ScrapeRequest) -> list[ListingCandidate]:
        """Fetch and parse AutoTempest listing candidates."""

        self.last_warnings = []
        self.last_errors = []
        if not request.base_url:
            self.last_errors.append("AutoTempest source requires a base_url")
            return []

        try:
            html = await self._fetch_html(request.base_url)
        except httpx.HTTPError as exc:
            logger.warning("autotempest fetch failed", extra={"source_id": request.source_id})
            self.last_errors.append(f"fetch failed: {exc}")
            return []
        except Exception as exc:
            logger.exception("autotempest unexpected fetch failure")
            self.last_errors.append(f"unexpected fetch failure: {exc}")
            return []

        api_candidates = await self._fetch_queue_candidates(
            html=html,
            base_url=request.base_url,
            source_name=request.source_name,
        )
        if api_candidates is not None:
            return api_candidates

        return self.parse_html(html, request.base_url, request.source_name)

    async def _fetch_html(self, url: str) -> str:
        """Fetch HTML with a polite user agent and no retries."""

        await self._respect_min_interval()
        headers = {"User-Agent": self.user_agent}
        if self.http_client is not None:
            response = await self.http_client.get(url, headers=headers)
            response.raise_for_status()
            self.last_request_at = time.monotonic()
            return response.text

        timeout = httpx.Timeout(self.timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            self.last_request_at = time.monotonic()
            return response.text

    async def _fetch_json(
        self,
        url: str,
        params: dict[str, Any],
        referer: str,
    ) -> dict[str, Any]:
        """Fetch JSON with a polite user agent and no retries."""

        await self._respect_min_interval()
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
            "Referer": referer,
        }
        if self.http_client is not None:
            response = await self.http_client.get(url, params=params, headers=headers)
            response.raise_for_status()
            self.last_request_at = time.monotonic()
            return response.json()

        timeout = httpx.Timeout(self.timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            self.last_request_at = time.monotonic()
            return response.json()

    async def _respect_min_interval(self) -> None:
        """Apply a minimal per-adapter request interval."""

        if self.last_request_at is None:
            return
        elapsed_seconds = time.monotonic() - self.last_request_at
        remaining_seconds = self.min_interval_seconds - elapsed_seconds
        if remaining_seconds > 0:
            await asyncio.sleep(remaining_seconds)

    def parse_html(
        self,
        html: str,
        base_url: str,
        source_name: str = "AutoTempest",
    ) -> list[ListingCandidate]:
        """Parse AutoTempest static HTML into listing candidates."""

        self.last_warnings = []
        self.last_errors = []
        try:
            soup = BeautifulSoup(html, "html.parser")
            candidates = self._parse_listing_cards(soup, base_url, source_name)
            if candidates:
                return candidates

            comparison_candidates = self._parse_comparison_links(soup, base_url)
            if comparison_candidates:
                self.last_warnings.append(
                    "static HTML exposed comparison links only; "
                    "no exact vehicle listing URLs found"
                )
                if self.capture_comparison_links:
                    return comparison_candidates
                return []

            self.last_warnings.append("no listing cards or comparison links found")
            return []
        except Exception as exc:
            logger.exception("autotempest parse failed")
            self.last_errors.append(f"parse failed: {exc}")
            return []

    async def _fetch_queue_candidates(
        self,
        html: str,
        base_url: str,
        source_name: str,
    ) -> list[ListingCandidate] | None:
        """Fetch AutoTempest queue-results JSON when page metadata is available."""

        try:
            search_params = _extract_search_params(html)
            if search_params is None:
                return None
            source_codes = _queue_source_codes(html)
            if not source_codes:
                return None
            candidates: list[ListingCandidate] = []
            for source_code in source_codes:
                params = _queue_params(search_params, source_code)
                queue_url = urljoin(base_url, "/queue-results")
                payload = await self._fetch_json(queue_url, params, base_url)
                if payload.get("status", 0) < 0:
                    self.last_warnings.append(f"{source_code} queue returned an error")
                    continue
                candidates.extend(
                    self._parse_queue_results(payload, source_code, source_name)
                )
            if "fbm" in _all_source_codes(html):
                self.last_warnings.append("skipped Facebook Marketplace source")
            if not candidates:
                self.last_warnings.append("AutoTempest queue returned no exact listings")
            return candidates
        except httpx.HTTPError as exc:
            logger.warning("autotempest queue fetch failed")
            self.last_warnings.append(f"queue fetch failed: {exc}")
            return None
        except Exception as exc:
            logger.exception("autotempest queue parse failed")
            self.last_errors.append(f"queue parse failed: {exc}")
            return []

    def _parse_queue_results(
        self,
        payload: dict[str, Any],
        source_code: str,
        source_name: str,
    ) -> list[ListingCandidate]:
        """Parse queue-results JSON into listing candidates."""

        candidates: list[ListingCandidate] = []
        for item in payload.get("results", []):
            if not isinstance(item, dict):
                continue
            candidate = _queue_item_to_listing(item, source_code, source_name)
            if candidate is not None:
                candidates.append(candidate)
        return candidates

    def build_source_test_result(
        self,
        listings: list[ListingCandidate],
    ) -> SourceTestResult:
        """Build a source-test result from the latest scrape state."""

        return SourceTestResult(
            url_accepted=not self.last_errors,
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

    def _parse_listing_cards(
        self,
        soup: BeautifulSoup,
        base_url: str,
        source_name: str,
    ) -> list[ListingCandidate]:
        """Parse full listing cards when static HTML contains them."""

        candidates: list[ListingCandidate] = []
        for card in _candidate_cards(soup):
            candidate = self._parse_listing_card(card, base_url, source_name)
            if candidate is not None:
                candidates.append(candidate)
        return candidates

    def _parse_listing_card(
        self,
        card: Tag,
        base_url: str,
        source_name: str,
    ) -> ListingCandidate | None:
        """Parse one listing card."""

        raw_text = _clean_text(card.get_text(" ", strip=True))
        link = _first_listing_link(card)
        if link is None:
            return None

        title = _extract_title(card, link)
        if not title:
            return None

        url = urljoin(base_url, str(link.get("href", "")))
        if not _is_exact_listing_url(url, base_url):
            return None
        price_amount = _extract_price(raw_text)
        mileage_value = _extract_mileage(raw_text)
        warnings = _field_warnings(price_amount, mileage_value)
        location_text = _extract_selector_text(card, [".location", "[data-location]"])
        return ListingCandidate(
            external_id=str(card.get("data-listing-id")) if card.get("data-listing-id") else None,
            title=title,
            url=url,
            description=raw_text,
            price_amount=price_amount,
            price_currency="USD" if price_amount is not None else None,
            mileage_value=mileage_value,
            mileage_unit="mi" if mileage_value is not None else None,
            location_text=location_text,
            source_name=source_name,
            raw_payload={
                "candidate_type": "vehicle_listing",
                "raw_text": raw_text,
                "warnings": warnings,
                "errors": [],
            },
        )

    def _parse_comparison_links(
        self,
        soup: BeautifulSoup,
        base_url: str,
    ) -> list[ListingCandidate]:
        """Parse comparison/outbound links from static AutoTempest HTML."""

        candidates: list[ListingCandidate] = []
        for link in soup.find_all("a", href=True):
            link_text = _clean_text(link.get_text(" ", strip=True))
            href = str(link.get("href"))
            if not _is_comparison_link(link_text, href):
                continue
            if _is_facebook_link(link_text, href):
                self.last_warnings.append("skipped Facebook comparison link")
                continue
            url = urljoin(base_url, href)
            label = _comparison_label(link_text)
            candidates.append(
                ListingCandidate(
                    title=f"AutoTempest comparison link: {label}",
                    url=url,
                    description=link_text,
                    source_name=label,
                    raw_payload={
                        "candidate_type": "comparison_link",
                        "raw_text": link_text,
                        "warnings": [
                            "comparison link only; static HTML did not include full listing data"
                        ],
                        "errors": [],
                    },
                )
            )
        return candidates


def _candidate_cards(soup: BeautifulSoup) -> list[Tag]:
    """Return likely listing cards."""

    cards: list[Tag] = []
    for tag in soup.find_all(["article", "div", "li"]):
        if not isinstance(tag, Tag):
            continue
        if not _has_vehicle_listing_marker(tag):
            continue
        if tag.find("a", href=True):
            cards.append(tag)
    return cards


def _extract_search_params(html: str) -> dict[str, Any] | None:
    """Extract AutoTempest search parameters from page JavaScript."""

    match = SEARCH_PARAMS_PATTERN.search(html)
    if match is None:
        return None
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _all_source_codes(html: str) -> list[str]:
    """Extract source codes declared in the AutoTempest results page."""

    soup = BeautifulSoup(html, "html.parser")
    source_codes: list[str] = []
    for section in soup.select(".source-results"):
        source_code = section.get("data-code")
        if isinstance(source_code, str) and source_code:
            source_codes.append(source_code)
    return source_codes


def _queue_source_codes(html: str) -> list[str]:
    """Return queue-results source codes supported by this adapter."""

    return [
        source_code
        for source_code in _all_source_codes(html)
        if source_code in QUEUE_SOURCE_CODES
    ]


def _queue_params(search_params: dict[str, Any], source_code: str) -> dict[str, Any]:
    """Build signed queue-results parameters for one AutoTempest source."""

    params = dict(search_params)
    params["sites"] = source_code
    params["deduplicationSites"] = "|".join(QUEUE_DEDUPE_SOURCE_CODES)
    params["rpp"] = 50
    params["searchAfter"] = "[]"
    params.pop("searchnum", None)
    unsigned_query = _jquery_param(params)
    params["token"] = hashlib.sha256(
        f"{unquote(unsigned_query)}{QUEUE_TOKEN_SECRET}".encode(),
    ).hexdigest()
    return params


def _jquery_param(params: dict[str, Any]) -> str:
    """Encode flat query params like jQuery.param for AutoTempest token input."""

    pairs = []
    for key, value in params.items():
        encoded_key = quote(str(key), safe=QUERY_SAFE_CHARS)
        encoded_value = quote(str(value), safe=QUERY_SAFE_CHARS)
        pairs.append(f"{encoded_key}={encoded_value}")
    return "&".join(pairs)


def _queue_item_to_listing(
    item: dict[str, Any],
    source_code: str,
    source_name: str,
) -> ListingCandidate | None:
    """Convert one queue-results object into a normalized listing candidate."""

    title = _clean_text(str(item.get("title") or ""))
    url = str(item.get("url") or "")
    if not title or not _is_http_url(url):
        return None
    price_amount = _extract_price(str(item.get("price") or ""))
    mileage_value = _extract_queue_mileage(str(item.get("mileage") or ""))
    listing_source_name = str(item.get("sourceName") or source_name)
    external_id = _queue_external_id(item)
    description = _queue_description(item)
    return ListingCandidate(
        external_id=external_id,
        title=title,
        url=url,
        description=description,
        price_amount=price_amount,
        price_currency="USD" if price_amount is not None else None,
        mileage_value=mileage_value,
        mileage_unit="mi" if mileage_value is not None else None,
        location_text=str(item.get("location") or "") or None,
        source_name=listing_source_name,
        raw_payload={
            "candidate_type": "queue_result",
            "listing_source_name": listing_source_name,
            "source_code": source_code,
            "backend_sitecode": item.get("backendSitecode"),
            "sitecode": item.get("sitecode"),
            "vin": item.get("vin"),
            "raw_text": description,
            "warnings": _field_warnings(price_amount, mileage_value),
            "errors": [],
        },
    )


def _queue_external_id(item: dict[str, Any]) -> str | None:
    """Return the strongest external identifier from queue-results data."""

    for key in ("id", "externalId", "vin"):
        value = item.get(key)
        if value:
            return str(value)
    return None


def _queue_description(item: dict[str, Any]) -> str:
    """Build compact raw text from queue-results fields."""

    fields = [
        item.get("title"),
        item.get("trim"),
        item.get("price"),
        item.get("mileage"),
        item.get("location"),
        item.get("dealerName"),
        item.get("sourceName"),
    ]
    fields.extend(_queue_detail_texts(item))
    return _clean_text(" ".join(str(field) for field in fields if field))


def _queue_detail_texts(item: dict[str, Any]) -> list[str]:
    """Extract descriptive queue fields used for keyword matching."""

    texts: list[str] = []
    details_text = _queue_details_text(item)
    if details_text:
        texts.append(details_text)
    detail_keys = [
        "description",
        "vehicleDescription",
        "sellerDescription",
        "dealerDescription",
        "sellerComments",
        "comments",
        "comment",
        "subtitle",
        "subTitle",
        "tagline",
        "headline",
        "transmission",
        "engine",
        "drivetrain",
        "exteriorColor",
        "interiorColor",
        "features",
        "options",
        "highlights",
    ]
    for key in detail_keys:
        texts.extend(_string_values(item.get(key)))
    return texts


def _queue_details_text(item: dict[str, Any]) -> str | None:
    """Combine AutoTempest's split visible details snippet."""

    text = "".join(
        str(item.get(key) or "")
        for key in ("detailsShort", "detailsMid", "detailsLong", "detailsExtraLong")
    )
    cleaned_text = _clean_html_text(text)
    return cleaned_text or None


def _string_values(value: Any) -> list[str]:
    """Flatten common JSON text shapes without including unrelated fields."""

    if value is None:
        return []
    if isinstance(value, str):
        text = _clean_html_text(value)
        return [text] if text else []
    if isinstance(value, (int, float, bool)):
        return []
    if isinstance(value, list):
        texts: list[str] = []
        for entry in value:
            texts.extend(_string_values(entry))
        return texts
    if isinstance(value, dict):
        texts: list[str] = []
        for nested_key in ("name", "label", "title", "description", "value", "text"):
            texts.extend(_string_values(value.get(nested_key)))
        return texts
    return []


def _clean_html_text(text: str) -> str:
    """Normalize text that may contain short HTML snippets."""

    if "<" in text and ">" in text:
        return _clean_text(BeautifulSoup(text, "html.parser").get_text(" ", strip=True))
    return _clean_text(text)


def _is_http_url(url: str) -> bool:
    """Return whether a URL is an absolute HTTP(S) URL."""

    parsed_url = urlparse(url)
    return parsed_url.scheme in {"http", "https"} and bool(parsed_url.netloc)


def _has_vehicle_listing_marker(tag: Tag) -> bool:
    """Return whether an element looks like a concrete vehicle listing card."""

    classes = tag.get("class", [])
    class_text = " ".join(classes if isinstance(classes, list) else [str(classes)])
    marker = " ".join(
        [
            class_text,
            str(tag.get("id", "")),
            "data-listing-id" if tag.get("data-listing-id") else "",
            "data-vin" if tag.get("data-vin") else "",
        ]
    ).casefold()
    excluded_markers = [
        "results-wrap",
        "results-target",
        "results-notice",
        "jump-list",
        "no-results",
        "external-link",
        "loading",
    ]
    if any(excluded_marker in marker for excluded_marker in excluded_markers):
        return False
    concrete_markers = [
        "vehicle-listing",
        "listing-card",
        "result-card",
        "vehicle-card",
        "data-listing-id",
        "data-vin",
    ]
    return any(concrete_marker in marker for concrete_marker in concrete_markers)


def _first_listing_link(card: Tag) -> Tag | None:
    """Return the first non-empty link in a listing card."""

    link = card.select_one("a.listing-link[href], a[href]")
    return link if isinstance(link, Tag) else None


def _is_exact_listing_url(url: str, base_url: str) -> bool:
    """Return whether a URL is not just the source search page or a fragment."""

    clean_url = urldefrag(url).url
    clean_base_url = urldefrag(base_url).url
    if clean_url == clean_base_url:
        return False
    if url.startswith("#"):
        return False
    parsed_url = urlparse(clean_url)
    if parsed_url.netloc.endswith("autotempest.com"):
        normalized_path = parsed_url.path.rstrip("/")
        if normalized_path in {"", "/results", "/compare"}:
            return False
    return True


def _extract_title(card: Tag, link: Tag) -> str:
    """Extract listing title."""

    title = _extract_selector_text(card, ["h1", "h2", "h3", ".title", "[data-title]"])
    if title:
        return title
    return _clean_text(link.get_text(" ", strip=True))


def _extract_selector_text(card: Tag, selectors: list[str]) -> str | None:
    """Extract text from the first matching selector."""

    for selector in selectors:
        match = card.select_one(selector)
        if match is not None:
            text = _clean_text(match.get_text(" ", strip=True))
            if text:
                return text
    return None


def _extract_price(raw_text: str) -> Decimal | None:
    """Extract a USD price from raw text."""

    match = PRICE_PATTERN.search(raw_text)
    if match is None:
        return None
    return Decimal(match.group(1).replace(",", "")).quantize(Decimal("0.01"))


def _extract_mileage(raw_text: str) -> int | None:
    """Extract mileage from raw text."""

    match = MILEAGE_PATTERN.search(raw_text)
    if match is None:
        return None
    return int(match.group(1).replace(",", ""))


def _extract_queue_mileage(raw_text: str) -> int | None:
    """Extract mileage from queue-results mileage text."""

    mileage_value = _extract_mileage(f"{raw_text} mi")
    if mileage_value is not None:
        return mileage_value
    digits = re.sub(r"[^\d]", "", raw_text)
    return int(digits) if digits else None


def _field_warnings(price_amount: Decimal | None, mileage_value: int | None) -> list[str]:
    """Return warnings for missing optional listing fields."""

    warnings: list[str] = []
    if price_amount is None:
        warnings.append("price missing")
    if mileage_value is None:
        warnings.append("mileage missing")
    return warnings


def _is_comparison_link(link_text: str, href: str) -> bool:
    """Return whether a link looks like an AutoTempest comparison link."""

    lower_text = link_text.casefold()
    lower_href = href.casefold()
    return (
        lower_text.startswith("open ")
        and "results" in lower_text
        or "autotempest.com/compare" in lower_href
        or "searchtempest.com" in lower_href
    )


def _is_facebook_link(link_text: str, href: str) -> bool:
    """Return whether a link points to Facebook Marketplace."""

    haystack = f"{link_text} {href}".casefold()
    return "facebook" in haystack


def _comparison_label(link_text: str) -> str:
    """Convert comparison link text into a source label."""

    label = link_text
    if label.casefold().startswith("open "):
        label = label[5:]
    if label.casefold().endswith(" results"):
        label = label[:-8]
    return label.strip() or "Comparison Site"


def _clean_text(text: str) -> str:
    """Normalize whitespace."""

    return " ".join(text.split())
