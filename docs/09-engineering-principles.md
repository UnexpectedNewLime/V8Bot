# Engineering Principles

## Core Philosophy

- Treat Discord as an interface, not the application core.
- Keep watch management, source management, scraping, dedupe, and digest state
  testable without Discord.
- Treat scraping as unreliable input.
- Prefer deterministic behavior over cleverness.
- Prefer polite static source adapters over browser automation.
- Keep local runtime data and secrets out of git.

## Layered Architecture

Dependency direction:

```text
bot -> services -> repositories -> database
                  -> scrapers
                  -> core helpers
scheduler -> services
```

Rules:

- `bot/` must not access repositories or SQLAlchemy models directly.
- Services own business logic and orchestration.
- Repositories own persistence details.
- Scrapers extract listing candidates only.
- Scheduler jobs delegate to services.
- Cross-layer shortcuts are not allowed for convenience.

## Data Flow

Normal scheduled collection:

1. Scheduler invokes `collect_listings_job`.
2. `ScrapeService` selects active watches and enabled sources.
3. Registered adapters return `ListingCandidate` rows.
4. Services score, filter, convert, dedupe, and persist matches.
5. Later, scheduler invokes `send_due_digests_job`.
6. `NotificationService` builds stored digest payloads and sends them through a
   `DigestSender`.
7. Successful sends mark watch listings sent.

Manual scrape flow:

1. Discord command calls `ListingService.scrape_watch_now`.
2. The same scrape service path stores matches.
3. The command posts newly pending listings to the watch thread.
4. The command marks those posted listings sent.

## Idempotency

Scraping must be safe to run repeatedly.

Rules:

- Re-running a scrape must not duplicate listing rows for the same source URL.
- Re-running a scrape must not duplicate watch-listing rows.
- Existing listings should be refreshed on rediscovery.
- Posted or digested listings should be marked sent.
- Unique database constraints should backstop service-level dedupe.

## Scheduling

Scraping and notification are separate systems.

Rules:

- Scheduled scraping stores listings silently.
- Scheduled digests read stored pending listings only.
- Digest sends must not scrape live websites.
- A failed scrape must not block a later digest from sending already-persisted
  listings.
- Due digest checks must not send the same watch twice in the same local minute.

## Source Isolation

Each source adapter is isolated.

Rules:

- A failure in one adapter call should be recorded and contained.
- A source without a registered adapter is skipped, not guessed.
- Diagnostic source tests are not production scrapers.
- Source-specific parsing belongs inside that source adapter.
- New sources should require adapter registration and source-kind inference, not
  changes throughout watch or digest logic.

## Testability

Core logic must be easy to test without Discord or live network calls.

Rules:

- Use in-memory SQLite for repository/service tests.
- Use fake senders for notification tests.
- Use saved HTML fixtures or mocked transports for parser tests.
- Use fixed conversion rates.
- Use explicit datetimes for notification scheduling tests.
- Redesign features that cannot be tested without Discord API access.

## Failure Handling

Scrape failures are normal.

Rules:

- Scrape failures must not crash the bot.
- User-facing errors must be structured and safe.
- Internal logs may include exception details but must not leak secrets.
- Failed digest sends should leave pending listings retryable unless a partial
  send strategy is explicitly implemented.
- Unsupported domains should return diagnostics without enabling scheduled
  scraping.

## Future Compatibility

The current implementation is Discord-first, but service boundaries should stay
interface-neutral enough for future reuse.

Rules:

- Do not pass Discord interactions into services.
- Keep user ownership explicit.
- Keep DTOs and dataclasses free of Discord-specific types unless they live in
  `bot/`.
- New presentation formats should not modify scraper or repository behavior.
- New storage queries belong in repositories.
