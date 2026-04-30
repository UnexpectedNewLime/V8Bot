# Testing Plan

## Current Test Posture

The repository uses pytest. Tests are local, deterministic, and do not require
Discord credentials or live website requests. Database tests use in-memory
SQLite. Scraper tests use saved fixtures or mocked `httpx` transports.

Primary checks:

```bash
pytest
python -m compileall src tests scripts
```

For documentation-only changes, use filesystem checks and `git status --short`.

## Existing Coverage Areas

### Configuration And Startup

- Bot client command registration.
- Runtime scraper adapter registration.
- Scheduler job registration.
- Database initialization and the `thread_id` compatibility column.

### Watch Service

- Keyword CSV parsing.
- Notification time validation.
- Watch creation with defaults.
- Delivery target and thread id persistence.
- Watch listing by user.
- Ownership checks on deactivation.

### Source Service

- Source URL validation.
- Source tests that pass, warn, or fail.
- Source test attempt persistence.
- Add-source source tests.
- Domain-derived source names.
- Generated source name uniqueness.
- Existing source reuse for the same URL.
- Duplicate name rejection for a different URL.
- Known source-kind inference for AutoTempest, Cars On Line, Corvette Magazine,
  and VetteFinders.
- Diagnostic source tests for unsupported domains.
- Runtime rejection of unregistered source kinds when disabled.
- Source removal from a watch.

### Scrape And Listing Services

- Mock scraper candidate shape.
- Matching and exclusion behavior.
- Repeated scrape dedupe.
- Listing refresh on rediscovery.
- Excluded keyword changes marking pending rows `excluded`.
- Immediate scrape summary counts.
- New pending listing id tracking.
- Skipped source warnings when no adapter is registered.
- Listing history including sent rows.

### Digest And Notification

- Digest payload construction.
- Empty digest behavior.
- Marking listings sent.
- Source name display from raw payload and known domains.
- Whole-number price formatting with commas.
- Listing history payloads.
- Due digest detection by local watch time.
- No duplicate scheduled sends in the same local minute.
- No-update messages for empty due digests.
- Persisting resolved thread ids.

### Discord Presentation

- Registered slash command names.
- Ephemeral message splitting.
- Multi-URL parsing from command fields.
- Markdown link URL extraction.
- Source-name validation for multi-URL input.
- Compact source-add summaries.
- Listing embed field shape.
- Per-watch thread names, reuse, unarchiving, and replacement after deletion.

### Scraper Adapters

- AutoTempest listing-card parsing.
- AutoTempest comparison-link handling.
- AutoTempest queue-results parsing.
- Guarding against treating search URLs as exact listings.
- HTTP error handling.
- Cars On Line fixture parsing.
- VetteFinders fixture parsing.
- Corvette Magazine fixture parsing.
- Static adapter mocked transport behavior.
- Diagnostic scraper warnings and sampled links.

## Test Data Safety

- Do not read real `.env` secrets in assertions or output.
- Do not require Discord API access in automated tests.
- Do not make live HTTP calls in automated tests.
- Use fake clocks or explicit datetimes for notification tests.
- Use fixed conversion rates in tests.
- Keep parser fixtures under `tests/fixtures/`.

## Expectations For New Work

Add focused tests when changing:

- Command names, options, response formatting, or Discord routing.
- Watch/source validation rules.
- Source-kind inference.
- Scraper parsing.
- Scheduled job intervals.
- Database schema or repository behavior.
- Listing dedupe, scoring, exclusion, or sent-state logic.
- Currency or mileage conversion.

Prefer the smallest test that proves the behavior. Use service-level tests over
Discord API integration tests whenever possible.

## Manual QA

Manual Discord QA is still useful before treating runtime changes as production
ready:

- Bot starts with a valid token.
- Guild slash commands sync.
- `/watch_add` creates a watch and, with source URLs, can run the initial scrape.
- Watch-specific threads are created and reused.
- `/watch_source_add` accepts known supported source URLs.
- `/watch_source_test` returns diagnostics for unsupported URLs.
- `/watch_scrape_now` posts only new listing embeds.
- Scheduled digest posts pending listings at the configured local time.
- Empty due digests post a no-update message.
- Duplicate listings are not resent by scheduled digests.
