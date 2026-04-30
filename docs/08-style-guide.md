# Style Guide

## Purpose

This guide defines coding standards for the current `car_watch_bot` package.
Follow existing local patterns before introducing new abstractions.

## Naming Conventions

- Use `snake_case` for functions, variables, modules, and database columns.
- Use `PascalCase` for classes, dataclasses, SQLAlchemy models, enums, and
  exceptions.
- Use `UPPER_SNAKE_CASE` only for true constants.
- Avoid vague names such as `data`, `item`, `thing`, `object`, `result2`, or
  `manager`.
- Prefer names that describe the domain object and action.

Domain naming:

- `Watch`: a user's saved car search.
- `Source`: a listing origin attached to a watch.
- `Listing`: a normalized listing discovered from a source.
- `WatchListing`: the watch/listing delivery state row.
- `ScrapeAttempt`: one adapter call result.
- `SourceTestAttempt`: one user-triggered source test.

## Project Structure Rules

- `bot/` handles Discord startup, commands, interaction deferral, embeds, and
  thread routing.
- `services/` contains business workflows and transaction boundaries.
- `db/repositories.py` handles database reads and writes.
- `scrapers/` extracts listing candidates and source-test diagnostics.
- `scheduler/` triggers services.
- `core/` contains dataclasses and pure helpers.

Do not:

- Import Discord interaction objects into services, repositories, scrapers, or
  scheduler code.
- Query SQLAlchemy models directly from command handlers.
- Write to the database from scrapers.
- Put Discord presentation formatting in services.
- Send Discord messages from scrapers.

## Function Design

- Keep functions small and single-purpose.
- Type hints are required for functions and methods.
- Use explicit parameters and return values.
- Prefer dependency injection over importing global service instances.
- Keep validation close to service boundaries.
- Make side effects visible in names or service boundaries.
- Keep comments short and useful.

## Error Handling

- Scrape failures must not crash the bot or scheduler.
- Expected business failures should use domain-specific exceptions such as
  `WatchValidationError` or `SourceValidationError`.
- Source tests should return structured warnings/errors.
- Scheduled scraper adapter failures should be recorded as `ScrapeAttempt` rows.
- User-facing command errors should be concise and safe.
- Do not expose stack traces or raw sensitive details to Discord users.

## Logging

- Use the standard logging module through the project logging configuration.
- Do not use `print` in application code.
- Include identifiers when available:
  - `user_id`.
  - `discord_user_id`.
  - `watch_id`.
  - `source_id`.
  - `listing_id`.
  - `scrape_attempt_id`.
- Never log Discord bot tokens, cookies, authorization headers, secrets, or full
  `.env` values.

## Scraper Rules

- Every production scraper must implement `ScraperAdapter`.
- Scrapers return `ListingCandidate` rows only.
- Scrapers must not score, rank, or filter listings for a watch.
- Scrapers must not write rows or send messages.
- Use polite `httpx` requests with configured user agent, timeout, and minimum
  interval.
- Keep source-specific parsing in source-specific adapter modules.
- Use fixtures or mocked transports in tests.
- Do not add adapters that require browser automation or challenge bypassing.
- Diagnostic source tests must not become production scraping.

## Discord Command Rules

- Commands call services only.
- Commands defer responses for service work.
- Configuration responses are ephemeral.
- Listing output goes to watch-specific public threads.
- Commands must scope watches and sources to the interacting user.
- Keep command text compact and split long ephemeral messages.
- Use `build_listing_embed` for listing embeds.

## Configuration Rules

- All runtime configuration comes through environment variables, `.env`, or
  `Settings`.
- Defaults belong in `config.py`.
- Keep `.env.example` aligned when adding or removing settings.
- Do not hardcode secrets or user-specific Discord ids.
- Do not hardcode local production URLs in services.

## Formatting

- Use black-compatible formatting.
- Keep imports organized and unused imports removed.
- Prefer explicit return types, including `-> None`.
- Keep tests readable and deterministic.
- Do not add broad refactors while implementing a narrow change.
