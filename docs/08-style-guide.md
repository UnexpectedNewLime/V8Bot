# Style Guide

## Purpose

This guide defines coding standards for V8Bot. Human developers and LLM agents must follow it when adding or changing application code.

## Naming Conventions

- Use `snake_case` for functions, variables, modules, and database column attributes.
- Use `PascalCase` for classes, Pydantic models, SQLAlchemy models, enums, and exceptions.
- Use `UPPER_SNAKE_CASE` only for true constants.
- Avoid vague names such as `data`, `item`, `thing`, `object`, `result2`, or `manager`.
- Prefer names that describe the domain object and action.

Domain naming:

- Use `Watch` for a user's saved search.
- Use `Source` for a listing origin, such as the mock source or a custom website source record.
- Use `Listing` for a normalized car listing discovered from a source.
- Use `WatchListing` for a listing matched to a watch and awaiting or recording delivery.
- Name services by business capability: `WatchService`, `SourceService`, `ScrapeService`, `DigestService`.
- Name repositories by persisted aggregate: `WatchRepository`, `SourceRepository`, `ListingRepository`.

## Project Structure Rules

- `bot/` handles Discord startup, slash commands, interaction deferral, permissions, and response presentation only.
- `core/services/` contains business logic and orchestration.
- `db/repositories/` handles database reads and writes.
- `scrapers/` extracts raw listing candidates and normalizes scraper output.
- `scheduler/` triggers jobs and delegates to services.
- Do not import Discord interaction objects into core, db, scraper, or scheduler business logic.
- Do not query SQLAlchemy models directly from Discord command handlers.
- Do not write to the database from scrapers.
- Do not put presentation formatting in services except service-neutral DTO fields.

## Function Design Rules

- Keep functions small and single-purpose.
- No function should exceed 50 lines without a strong reason.
- Use explicit parameters and return values.
- Type hints are required for every function and method.
- Avoid hidden side effects. If a function writes to the database, sends Discord messages, schedules jobs, or performs network I/O, make that clear in the function name or service boundary.
- Prefer dependency injection over importing global service instances.
- Keep validation close to service boundaries.

## Error Handling

- Scrape failures must never crash the bot or scheduler.
- Return structured errors from services and source tests.
- Record failed scheduled scrapes as `ScrapeAttempt` records.
- Record source test failures as `SourceTestAttempt` records.
- Use domain-specific exceptions for expected business failures, such as invalid watch input or unsupported source URL.
- Log warnings for recoverable external issues, such as a timeout from one source.
- Log errors for unexpected failures, data corruption, failed digest delivery, or repeated job failures.
- Do not expose stack traces or raw exception messages to Discord users.

## Logging

- Use structured logging through the project logging module.
- Do not use `print`.
- Include relevant identifiers when available:
  - `user_id`
  - `discord_user_id`
  - `watch_id`
  - `source_id`
  - `listing_id`
  - `digest_batch_id`
  - `scrape_attempt_id`
- Never log Discord bot tokens, secrets, cookies, authorization headers, or full `.env` values.
- Log enough context to debug failures without leaking private user configuration unnecessarily.

## Testing Expectations

- Every core module must have tests.
- Repository behaviour must be tested with temporary SQLite databases.
- Service behaviour must be tested without Discord API calls.
- Tests must not make live network calls by default.
- Use mocked `httpx` responses for source tests.
- Use saved HTML fixtures for future parser tests.
- Use deterministic mock scraper data.
- Use fixed currency rates in tests.
- Add regression tests for dedupe, pending digest state, failed scrape attempts, and source activation/deactivation.

## Scraper Rules

- Every scheduled scraper must implement the base scraper interface.
- Scrapers must return normalized `ListingCandidate` or `NormalizedListing` objects defined by the scraper/core boundary.
- Scrapers must not score, rank, or filter listings for a watch.
- Scrapers must not write to the database directly.
- Scrapers must not send Discord messages.
- Source-specific parsing belongs in source-specific adapter modules.
- MVP scheduled scraping must use only the mock scraper.
- Custom source tests may inspect a page but must not create listings or register production adapters.

## Discord Command Rules

- Commands must call the service layer only.
- Do not put business logic in command handlers.
- Do not access repositories directly from command handlers.
- Defer responses for operations that may exceed Discord interaction timing.
- Configuration responses should be ephemeral.
- Responses must be clear, structured, and user-safe.
- Scheduled digests are the only place listings are sent to users in MVP.
- Command handlers must scope watches and user-owned sources to the interacting Discord user.

## Configuration Rules

- All configuration must come through `.env`, environment variables, or the config module.
- Do not hardcode secrets.
- Do not hardcode user-specific Discord ids outside local ignored config.
- Do not hardcode production source URLs in services or scrapers.
- Defaults belong in the config module, not scattered across command handlers.

## Formatting

- Use black-compatible formatting.
- Keep imports organized and unused imports removed.
- Type hints are required for all functions and methods.
- Prefer explicit return types, including `-> None`.
- Keep comments short and useful.
- Do not add broad refactors while implementing a narrow change.
