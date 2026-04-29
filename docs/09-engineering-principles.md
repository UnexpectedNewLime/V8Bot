# Engineering Principles

## Purpose

This document defines architectural and design rules for V8Bot. These rules are intentionally strict. If a proposed implementation violates them, change the implementation, not the rule, unless the product requirements are explicitly revised.

## Core Philosophy

- Build for correctness first, scraping later.
- Develop mock-first. The mock scraper must prove the data flow before any real scraper exists.
- Prefer deterministic behaviour over cleverness.
- Make boring, testable choices.
- Treat scraping as unreliable input, not as the core product.
- The core product is reliable watch management, dedupe, persistence, and scheduled digest delivery.

## Layered Architecture

The dependency direction is strict:

```text
bot -> services -> repositories -> database
```

Rules:

- `bot/` must never access the database directly.
- `bot/` must never import SQLAlchemy models or repositories.
- `bot/` may call services and presenters only.
- Services contain business logic and orchestration.
- Repositories contain database access and persistence rules.
- Database models do not contain Discord command behaviour.
- Scrapers must not know about Discord.
- Scrapers must not know about the database.
- Scrapers must not send messages, write rows, schedule jobs, or update watch state.
- Cross-layer shortcuts are not allowed for convenience.

## Data Flow Rules

The normal collection flow is:

1. Scrapers produce raw listing candidates.
2. Services normalize, validate, filter, score when scoring exists, convert units and currency, and decide what should be persisted.
3. Repositories persist listings, matches, attempts, and delivery state.
4. Digest services read persisted data only.
5. Discord presenters render digest payloads for users.

Rules:

- Scrapers extract listing data only.
- Services enrich and coordinate.
- Repositories persist.
- Digests must not call scrapers.
- Digests must not inspect live websites.
- Digest output must be reproducible from stored data.

## Idempotency

Scraping must be safe to run repeatedly.

Rules:

- Re-running a scrape must not duplicate listings.
- Re-running a scrape must not duplicate pending watch deliveries.
- Dedupe must be enforced at repository and database constraint level, not only in memory.
- Use source id plus external id, canonical URL, or content hash for listing identity.
- Use unique watch-listing relationships for per-watch delivery identity.
- Services should treat duplicate insert attempts as expected behaviour.

## Scheduling Rules

Scraping and notifications are separate systems.

Rules:

- Scraping jobs collect and store listings silently.
- Notification jobs read stored pending listings.
- Notification jobs must not scrape.
- Scraping jobs must not send Discord messages.
- No real-time listing alerts in MVP.
- Scheduled digest delivery is the only MVP notification path.
- A failed scrape must not block a later digest from sending already persisted listings.

## Source Isolation

Each source must be isolated.

Rules:

- Each scraper adapter is independent.
- A failure in one source must not stop other sources from running.
- Source-specific parsing must stay inside that source adapter.
- Source-specific failures must be recorded as scrape attempts.
- No source adapter may mutate shared scraper state in a way that affects another source.
- A source without a registered adapter must be skipped, not guessed.
- Custom website source tests must not be treated as production scrapers.

## Extensibility

New features should attach to existing boundaries.

Rules:

- Adding a new source should require changes in `scrapers/` and adapter registration only.
- Adding a new source must not require changes to watch logic, digest logic, Discord commands, or repositories, unless the shared adapter interface itself changes.
- Adding a new command should not modify core business logic.
- Commands should expose existing service capabilities.
- New presentation formats should not modify services.
- New storage queries belong in repositories, not command handlers or scrapers.

## Testability

Core logic must be easy to test without Discord or network access.

Rules:

- All core logic must be testable without connecting to Discord.
- All core logic must be testable without live network calls.
- Services should be pure or near-pure where possible.
- Time, currency rates, scraper adapters, and Discord senders must be injectable.
- Tests should use fake clocks, fake senders, deterministic scraper output, and temporary SQLite databases.
- Parser tests for future real scrapers must use saved HTML fixtures.
- A feature that cannot be tested without Discord should be redesigned.

## Failure Handling

Scraping failures are normal.

Rules:

- The system must degrade gracefully when a source fails.
- A scrape failure must not crash the bot.
- A scrape failure must not stop unrelated watches or sources.
- Failed scrapes must be recorded for diagnostics.
- User-facing errors must be structured and safe.
- Internal logs may include exception details, but must not leak secrets.
- Failed digest sends must leave pending listings retryable unless a partial send is explicitly handled.

## Future Compatibility

Discord is one interface, not the application core.

Rules:

- Design services so a future web UI can reuse them.
- Do not pass Discord interaction objects into services.
- Do not bake Discord response formatting into core models.
- Keep user ownership explicit and interface-neutral.
- Keep DTOs independent of Discord-specific types unless they live in `bot/`.
- A future website should be able to create watches, manage sources, inspect attempts, and render digests through the same service layer.
