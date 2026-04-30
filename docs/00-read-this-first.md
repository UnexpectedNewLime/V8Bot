# Read This First

## Current Purpose

This repository is a working Python 3.11+ Discord bot prototype for car listing
watches. The importable package is `car_watch_bot`. Users create watches from
Discord, attach supported listing sources, scrape those sources manually or on a
schedule, and receive listing embeds in watch-specific Discord threads.

The current implementation is no longer only a planning skeleton. These docs
describe the code that exists now.

## Current Runtime Shape

- Discord runtime and slash commands live under `src/car_watch_bot/bot/`.
- Business logic lives under `src/car_watch_bot/services/`.
- SQLAlchemy setup, models, and repositories live under `src/car_watch_bot/db/`.
- Scraper adapters live under `src/car_watch_bot/scrapers/`.
- APScheduler jobs live under `src/car_watch_bot/scheduler/`.
- Local scripts live under `scripts/`.
- Tests live under `tests/` and use in-memory SQLite plus mocked HTTP clients.

## Current Capabilities

- Watches store a car query, included keywords, excluded keywords, notification
  time, preferred currency, distance unit, Discord channel, and resolved thread.
- Sources can be added to a watch from one or more URLs. Blank names are derived
  from the domain and made unique per user.
- Registered scheduled source kinds are `mock`, `autotempest`, `cars_on_line`,
  `corvette_magazine`, and `vettefinders`.
- Unsupported URLs can be tested diagnostically, but runtime source addition is
  configured to reject unregistered source kinds.
- Manual commands can scrape immediately and post new listing embeds to the
  watch thread. Posted listings are then marked sent.
- Scheduled scrape collection stores matching listings silently.
- Scheduled digest checks post pending listings, or a no-update confirmation,
  when a watch's local notification time is due.
- Discord output is routed to a per-watch public thread named from the watch
  query and keywords.

## Non-Negotiable Rules

- Do not log, print, commit, or copy secrets from `.env`.
- Do not support Facebook Marketplace in this version.
- Do not bypass anti-bot or challenge systems.
- Do not treat unsupported diagnostic source tests as production scrapers.
- Do not put Discord interaction objects in services, repositories, scrapers, or
  scheduler business logic.
- Do not let scrapers write to the database or send Discord messages.
- Do not bypass the service layer from Discord commands.
- Do not add a web dashboard or plugin architecture unless explicitly requested.

## Important Current Limitations

- There is no migration framework. `init_database` creates tables and includes
  one compatibility helper that adds `watches.thread_id` to older local SQLite
  databases.
- There is no `DigestBatch` table in the current schema. Digest state is tracked
  through `watch_listings.status`, `watch_listings.sent_at`, and
  `watches.last_digest_sent_at`.
- Currency conversion is intentionally narrow: current service conversion only
  handles same-currency values and USD to AUD through `USD_TO_AUD_RATE`.
- Direct Cars.com, Gateway Classic Cars, and Streetside Classics adapters are
  not registered because polite HTTP requests receive challenge responses.
- Carsales has no adapter because there is not yet a concrete target URL and
  permission posture.

## Development Defaults

Use the README commands for setup and local running:

```bash
PYTHONPATH=src python -m car_watch_bot.main
pytest
python -m compileall src tests scripts
```

For docs-only changes, a filesystem sanity check and `git status --short` are
usually enough.

## When Docs Disagree

Prefer the current code and tests as the source of truth, then update these docs
as part of the same change. If the requested change is product-level rather than
a bug fix, update docs first so the intended behavior is explicit before code
changes follow.
