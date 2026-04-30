# Scraper Design

## MVP Position

MVP scheduled collection uses mock scraping by default. Real website adapters should be added behind stable scraper boundaries so watch, digest, and deduplication services do not need source-specific changes.

Current real adapters are `AutoTempestScraper`, `CarsOnLineScraper`,
`CorvetteMagazineScraper`, and `VetteFindersScraper`. They are implemented for
manual/local use and fixture-tested parsing, but sources are only scraped when a
watch is explicitly attached to a matching source kind. They must use polite
`httpx` requests, configured timeout and user agent values, and no anti-bot
bypasses.

Direct Cars.com, Gateway Classic Cars, and Streetside Classics adapters are not
registered because simple polite HTTP requests currently receive challenge
responses. Carsales is also not registered because there is no concrete target
URL yet.

Custom source tests are allowed in MVP and may make a single diagnostic fetch
with `httpx`, then inspect the response with BeautifulSoup. That behaviour is a
source validation tool, not scheduled production scraping. Unsupported domains
should report that no scheduled adapter is registered, then include lightweight
diagnostics such as page title, link count, and sampled links from the polite
fetch.

Facebook Marketplace is explicitly out of scope for v1 and should be rejected by source validation.

## Scraper Adapter Interface

Suggested interface:

```python
from typing import Protocol

class ScraperAdapter(Protocol):
    @property
    def source_kind(self) -> str:
        ...

    async def fetch_listings(self, request: ScrapeRequest) -> list[ListingCandidate]:
        ...
```

Suggested request model:

```python
class ScrapeRequest(BaseModel):
    source_id: int
    source_name: str
    source_kind: str
    base_url: str | None
    source_config: dict
    watch_id: int
    included_keywords: list[str]
    excluded_keywords: list[str]
    criteria_version: int
```

Suggested candidate model:

```python
class ListingCandidate(BaseModel):
    external_id: str | None = None
    url: str
    title: str
    description: str | None = None
    price_amount: Decimal | None = None
    price_currency: str | None = None
    mileage_value: int | None = None
    mileage_unit: Literal["km", "mi"] | None = None
    location_text: str | None = None
    image_url: str | None = None
    seller_name: str | None = None
    listed_at: datetime | None = None
    raw_payload: dict = Field(default_factory=dict)
```

## Mock Scraper

The mock scraper should:

- Return deterministic listing candidates.
- Include at least one duplicate candidate across runs.
- Include multiple currencies.
- Include mileage in kilometres and miles.
- Include listings that match and do not match sample keywords.
- Include listings with excluded keywords for filter tests.
- Always include URLs.

Mock data should be small and easy to reason about. Tests should not depend on network access.

## Normalization

Normalization should produce a consistent listing shape before persistence:

- Trim whitespace.
- Normalize URLs where safe.
- Normalize currency codes to uppercase.
- Normalize mileage units to `km` or `mi`.
- Generate a content hash from stable fields.
- Preserve raw payload for debugging.

## Deduplication Strategy

Deduplication should happen before creating watch delivery rows.

Priority:

1. Same source and same external id.
2. Same source and canonical URL.
3. Same source and content hash.

Per-watch delivery dedupe:

- Use a unique `(watch_id, listing_id)` relationship.
- If a listing has already been sent for a watch, do not send it again.
- If a listing is rediscovered before digest time, update `last_seen_at` but keep one pending watch listing.

## Keyword Filtering

Filtering should be case-insensitive.

Match if:

- At least one included keyword appears in title or description.
- No excluded keyword appears in title or description.

Future versions may support structured filters such as price range, year range, make, model, transmission, and location radius.

## Source Test Behaviour

Source test exists to help users validate custom website sources before future real scraping support.

MVP behaviour:

- Reject unsupported domains, including Facebook Marketplace.
- Validate URL shape.
- Optionally fetch the page with `httpx`.
- Parse HTML with BeautifulSoup.
- Check whether the page has listing-like anchors, title text, and accessible content.
- Return a structured result with `status`, `notes`, and optional `detected_links`.
- Record a `SourceTestAttempt`.
- Do not persist listings.
- Do not create a real scraper adapter.
- Do not mark the source as production-scrapable.

Suggested statuses:

- `passed`: page is reachable and appears to contain listing-like links.
- `warning`: page is reachable but structure is unclear.
- `failed`: URL is invalid, blocked, unreachable, unsupported, or forbidden by v1 policy.

## Scrape Attempt Behaviour

Each scheduled adapter call should create a `ScrapeAttempt` record.

Rules:

- Mark successful adapter calls as `success`, including counts for seen, matched, and created listings.
- Mark adapter exceptions, timeouts, and parser failures as `failed`.
- Keep failed attempts silent for normal users in MVP.
- Do not send partial or failed scrape information in digests.
- If the scheduler encounters a source kind with no registered adapter, skip it before calling the scraper. Recording a `skipped` attempt is optional, but the scheduler must never treat a custom website source as mock data.

## Future Real Scraper Rules

When real scraping is added:

- Review source terms and robots policies.
- Prefer simple `httpx` + BeautifulSoup adapters where permitted.
- Add per-source rate limits.
- Add timeouts and retries with backoff.
- Identify stable listing ids when possible.
- Keep parser tests based on saved HTML fixtures.
- Keep source-specific parsing isolated to adapter modules.
