# Scraper Design

## Current Position

Scraping is implemented through adapter classes behind the `ScraperAdapter`
protocol. The bot currently registers:

- `MockScraper`.
- `AutoTempestScraper`.
- `CarsOnLineScraper`.
- `CorvetteMagazineScraper`.
- `VetteFindersScraper`.

The adapters are suitable for local/manual use and scheduled use only when a
watch is attached to a matching source kind. They use polite `httpx` requests,
configured timeouts, configured user agent, and a per-adapter minimum request
interval.

There is no browser automation, login flow, or challenge bypass.

## Unsupported Sources

Direct Cars.com, Gateway Classic Cars, and Streetside Classics adapters are not
registered because simple polite HTTP requests currently receive challenge
responses. Carsales is not registered because there is no concrete target URL
and permission posture yet.

Unsupported URLs are classified as `custom_website`. Runtime source addition
rejects unregistered source kinds. `/watch_source_test` can still run
`DiagnosticScraper`, which makes a single polite fetch, reports page-level
warnings, and samples links without enabling scheduled scraping.

Facebook Marketplace is explicitly unsupported and should be rejected.

## Adapter Interface

Current interface in `scrapers/base.py`:

```python
@dataclass(frozen=True)
class ScrapeRequest:
    source_id: int
    source_name: str
    source_kind: str
    base_url: str | None
    watch_id: int
    included_keywords: list[str]
    excluded_keywords: list[str]
    criteria_version: int


class ScraperAdapter(Protocol):
    @property
    def source_kind(self) -> str:
        ...

    async def fetch_listings(self, request: ScrapeRequest) -> list[ListingCandidate]:
        ...
```

Adapters return `ListingCandidate` dataclasses from `core/models.py`.

## Listing Candidate Shape

Current fields:

- `title`.
- `url`.
- `external_id`.
- `description`.
- `price_amount`.
- `price_currency`.
- `mileage_value`.
- `mileage_unit`.
- `location_text`.
- `source_name`.
- `listed_at`.
- `raw_payload`.

URL and title are the practical minimum for useful listing output. Price and
mileage are optional and produce warnings in source-test results when missing.

## Mock Scraper

The mock scraper returns four deterministic C5 Corvette candidates:

- A strong manual HUD targa match.
- An automatic convertible candidate intended to be excluded by common tests.
- A manual coupe missing mileage.
- A Z06 manual candidate missing price.

It is used by tests and can be used for local service checks.

## AutoTempest Adapter

`AutoTempestScraper` supports:

- Static listing-card parsing when exact cards are present.
- Queue-results JSON fetching when page metadata exposes supported source codes.
- Optional comparison link capture for manual debugging.
- Filtering out Facebook Marketplace comparison/queue content.
- Adapter-specific source-test warnings and errors.

By default, static comparison links are not returned as listings because they are
not exact vehicle listing URLs.

## Static HTML Adapters

The shared `StaticHtmlScraper` base provides:

- Polite HTML fetching.
- Minimum interval handling.
- Source-test result building.
- Common price and mileage extraction helpers.
- Raw payload warning helpers.

Current subclasses:

- `CarsOnLineScraper`: parses `li.job_listing` cards.
- `CorvetteMagazineScraper`: parses schema.org car classified cards.
- `VetteFindersScraper`: parses C5 summary rows.

## Diagnostic Scraper

`DiagnosticScraper` is for source testing unsupported domains. It:

- Reports that the domain is not supported for scheduled scraping.
- Fetches one page politely.
- Captures page title and link count.
- Samples up to five visible links as rough candidates.
- Builds a `SourceTestResult` with `url_accepted=False`.

Diagnostic output must never be treated as production scraping.

## Scoring And Filtering

Scrapers do not decide watch matches. `ScrapeService` passes candidates to
`score_listing`, which:

- Searches title and description.
- Rejects listings containing excluded keywords.
- Adds score for car query terms.
- Adds score for included keywords.
- Notes missing price or mileage.

Non-matching rediscovered listings can refresh the stored row and mark an
existing pending watch listing `excluded`.

## Persistence And Dedupe

Scrapers do not write to the database. `ScrapeService` and `ListingRepository`
handle persistence.

Current repository behavior:

- Finds existing listings by `(source_id, url)`.
- Stores `external_id`, with a database uniqueness constraint on
  `(source_id, external_id)`.
- Stores a content hash from title and URL.
- Uses unique `(watch_id, listing_id)` to prevent duplicate watch deliveries.
- Refreshes existing listing fields on rediscovery.

## Source Test Behavior

Source tests:

- Validate `http` or `https` URL shape.
- Reject Facebook domains.
- Use a registered adapter for known source kinds.
- Use diagnostics for unsupported domains when called from `/watch_source_test`.
- Store `SourceTestAttempt` rows.
- Never create `Listing` or `WatchListing` rows.

Accepted source tests may still include warnings for missing price or mileage.

## Future Adapter Rules

When adding a source:

- Confirm polite static access is viable.
- Respect site terms and robots policy.
- Use fixture-based parser tests.
- Add the adapter under `scrapers/`.
- Register it in `main._scraper_adapters`.
- Add source-kind inference in `SourceService`.
- Add tests for classification, parser output, source-test results, and runtime
  registration.
