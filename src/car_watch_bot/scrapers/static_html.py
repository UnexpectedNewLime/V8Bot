"""Shared helpers for static HTML scraper adapters."""

import asyncio
import logging
import re
import time
from decimal import Decimal
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
from bs4 import BeautifulSoup

from car_watch_bot.core.models import ListingCandidate, SourceTestResult


PRICE_PATTERN = re.compile(r"\$\s*([\d,]+(?:\.\d{2})?)")
MILEAGE_PATTERN = re.compile(
    r"([\d,]+(?:\.\d+)?)\s*(k)?\s*(?:mi|mile|miles)\b",
    re.IGNORECASE,
)


class StaticHtmlScraper:
    """Base behaviour for simple static HTML source adapters."""

    source_label = "static source"

    def __init__(
        self,
        user_agent: str,
        timeout_seconds: float = 10.0,
        min_interval_seconds: float = 2.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds
        self.min_interval_seconds = min_interval_seconds
        self.http_client = http_client
        self.last_request_at: float | None = None
        self.last_warnings: list[str] = []
        self.last_errors: list[str] = []

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

    async def _respect_min_interval(self) -> None:
        """Apply a minimal per-adapter request interval."""

        if self.last_request_at is None:
            return
        elapsed_seconds = time.monotonic() - self.last_request_at
        remaining_seconds = self.min_interval_seconds - elapsed_seconds
        if remaining_seconds > 0:
            await asyncio.sleep(remaining_seconds)

    def _handle_fetch_error(
        self,
        exc: Exception,
        source_id: int,
        logger: logging.Logger,
    ) -> list[ListingCandidate]:
        """Record a fetch failure and return an empty result."""

        logger.warning(
            "%s fetch failed",
            self.source_label,
            extra={"source_id": source_id},
        )
        self.last_errors.append(f"fetch failed: {exc}")
        return []

    def _handle_unexpected_fetch_error(
        self,
        exc: Exception,
        logger: logging.Logger,
    ) -> list[ListingCandidate]:
        """Record an unexpected fetch failure and return an empty result."""

        logger.exception("%s unexpected fetch failure", self.source_label)
        self.last_errors.append(f"unexpected fetch failure: {exc}")
        return []

    def build_source_test_result(
        self,
        listings: list[ListingCandidate],
    ) -> SourceTestResult:
        """Build a source-test result from the latest scraper state."""

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


def soup_from_html(html: str) -> BeautifulSoup:
    """Parse HTML with the repo-standard parser."""

    return BeautifulSoup(html, "html.parser")


def clean_text(text: str) -> str:
    """Normalize whitespace."""

    return " ".join(text.split())


def extract_price(raw_text: str) -> Decimal | None:
    """Extract a USD price from text."""

    match = PRICE_PATTERN.search(raw_text)
    if match is None:
        return None
    return Decimal(match.group(1).replace(",", "")).quantize(Decimal("0.01"))


def decimal_price(value: str | None) -> Decimal | None:
    """Convert a numeric price string into a decimal amount."""

    if not value:
        return None
    normalized_value = value.replace(",", "").strip()
    try:
        return Decimal(normalized_value).quantize(Decimal("0.01"))
    except Exception:
        return None


def extract_mileage(raw_text: str) -> int | None:
    """Extract mileage from text, including common K-mile shorthand."""

    match = MILEAGE_PATTERN.search(raw_text)
    if match is None:
        return None
    value = Decimal(match.group(1).replace(",", ""))
    if match.group(2):
        value *= Decimal("1000")
    return int(value)


def field_warnings(price_amount: Decimal | None, mileage_value: int | None) -> list[str]:
    """Return warnings for missing optional listing fields."""

    warnings: list[str] = []
    if price_amount is None:
        warnings.append("price missing")
    if mileage_value is None:
        warnings.append("mileage missing")
    return warnings


def query_value(url: str, key: str) -> str | None:
    """Return the first query value from a URL."""

    values = parse_qs(urlparse(url).query).get(key)
    if not values:
        return None
    return values[0]


def path_external_id(url: str) -> str | None:
    """Return the last path segment from a URL."""

    path_parts = [part for part in urlparse(url).path.split("/") if part]
    return path_parts[-1] if path_parts else None


def raw_payload(
    *,
    candidate_type: str,
    raw_text: str,
    price_amount: Decimal | None,
    mileage_value: int | None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build consistent raw scraper metadata."""

    payload: dict[str, Any] = {
        "candidate_type": candidate_type,
        "raw_text": raw_text,
        "warnings": field_warnings(price_amount, mileage_value),
        "errors": [],
    }
    if extra:
        payload.update(extra)
    return payload
