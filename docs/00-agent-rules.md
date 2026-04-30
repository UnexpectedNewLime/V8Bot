# Agent Rules

## Always Read First

Before changing code or docs, read:

- `.codex/instructions.md` when it exists.
- `docs/00-read-this-first.md`.
- `docs/08-style-guide.md`.
- `docs/09-engineering-principles.md`.

Also scan `.codex/commands/` and `.codex/skills/` when the task mentions a local
command, workflow, or skill.

## Current Repo Facts

- The package is `car_watch_bot`, not `v8bot`.
- The bot exposes compact slash commands such as `/watch_add`,
  `/watch_source_add`, and `/watch_scrape_now`.
- Listing messages are sent to per-watch public Discord threads.
- Scheduled scraping and scheduled digest delivery are separate jobs.
- Registered runtime scraper kinds are `mock`, `autotempest`, `cars_on_line`,
  `corvette_magazine`, and `vettefinders`.
- Unsupported domains are diagnostic-only unless a real adapter is added and
  registered.

## Never

- Never bypass the service layer from Discord command code.
- Never write business logic in command handlers.
- Never access repositories directly from command handlers.
- Never mix scraper parsing with persistence.
- Never let scrapers know about Discord or the database.
- Never add support for Facebook Marketplace in this version.
- Never bypass challenge pages, login walls, or anti-bot protections.
- Never commit `.env`, `.codex/`, local SQLite databases, scrape logs, or Docker
  runtime overrides.

## Feature Work

- Keep changes scoped to the requested behavior.
- Prefer existing service, repository, scraper adapter, and presenter patterns.
- Update docs when behavior, commands, schema, config, or supported source kinds
  change.
- Add or update tests for new core logic, repository behavior, scraper parsing,
  command formatting, or scheduler behavior.
- Keep core logic testable without Discord and without live network calls.

## Scraper Rules

- Add new production sources behind `ScraperAdapter`.
- Keep source-specific parsing inside source-specific adapter modules.
- Use polite `httpx` requests with configured timeout, user agent, and minimum
  interval.
- Use saved fixtures or mocked transports in tests.
- Treat scrape failures as expected input and record attempts where the service
  path reaches an adapter.
- Do not register direct sources that require browser automation or challenge
  bypassing.

## When Unsure

- Prefer the simpler implementation.
- Prefer explicit behavior over implicit behavior.
- Prefer deterministic tests over live integration checks.
- Ask only when a safe assumption is not possible.
