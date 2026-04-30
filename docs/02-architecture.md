# Architecture

## Overview

V8Bot is a standalone Discord bot with a layered Python package named
`car_watch_bot`. Discord command handlers are thin adapters over services.
Services coordinate repositories, scraper adapters, conversion helpers, digest
formatting, and notification senders.

The design still keeps the core reusable outside Discord: services do not accept
Discord interaction objects, scrapers do not know about Discord or the database,
and repositories own SQLAlchemy access.

## Technology Stack

- Python 3.11+.
- `discord.py` for bot runtime and slash commands.
- SQLAlchemy with SQLite for persistence.
- APScheduler for scrape and digest intervals.
- Pydantic Settings for environment configuration.
- `httpx` and BeautifulSoup for polite static HTML source adapters and
  diagnostics.
- pytest for automated tests.

## Actual Folder Structure

```text
src/car_watch_bot/
  main.py
  config.py
  logging_config.py

  bot/
    client.py
    commands.py
    embeds.py
    watch_threads.py
    threads.py

  core/
    conversions.py
    digest.py
    models.py
    scoring.py

  db/
    database.py
    models.py
    repositories.py

  scrapers/
    base.py
    mock.py
    static_html.py
    diagnostic.py
    autotempest.py
    cars_on_line.py
    corvette_magazine.py
    vettefinders.py

  scheduler/
    jobs.py

scripts/
  local_scrape_flow.py
  local_watch_flow_check.py
  manual_autotempest_scrape.py

tests/
```

## Dependency Direction

The intended dependency direction is:

```text
bot -> services -> repositories -> database
                  -> scrapers
                  -> core helpers
scheduler -> services
```

Rules:

- `bot/` registers slash commands, defers interactions, formats responses, and
  sends Discord embeds.
- `services/` owns business workflows and transaction boundaries.
- `db/repositories.py` owns persistence operations.
- `scrapers/` extracts listing candidates only.
- `core/` contains interface-neutral dataclasses and pure helpers.
- `scheduler/` triggers services.

## Runtime Assembly

`car_watch_bot.main` loads settings, initializes the SQLite schema, builds a
session factory, creates scraper adapters, constructs services, creates the
Discord client, wires the notification sender, and starts APScheduler during the
Discord setup hook.

Runtime scraper adapters are currently registered for:

- `mock`.
- `autotempest`.
- `cars_on_line`.
- `corvette_magazine`.
- `vettefinders`.

`SourceService` is configured at runtime with `allow_unregistered_sources=False`.
That means unsupported domains can be tested diagnostically with
`/watch_source_test`, but they cannot be attached to watches for scheduled
scraping.

## Discord Layer

The Discord layer owns:

- Bot startup and command tree sync.
- Slash command registration.
- Interaction deferral and ephemeral responses for configuration commands.
- Listing embed construction.
- Per-watch thread resolution, creation, unarchiving, and reuse.
- Digest sending through `DiscordDigestSender`.

The current command names are flat underscore commands, not nested command
groups. See `docs/04-command-design.md`.

## Service Layer

Current services:

- `WatchService`: creates, lists, updates, deactivates, and resolves delivery
  targets for watches.
- `SourceService`: validates URLs, infers source kinds, runs source tests,
  creates/reuses sources, and attaches/removes them from watches.
- `ListingService`: runs user-triggered scrapes, lists visible watch listings,
  and marks posted listings sent.
- `ScrapeService`: runs scheduled or explicit scrape orchestration for active
  watch-source pairs.
- `DigestService`: builds digest/listing payloads from stored rows and marks
  rows sent.
- `NotificationService`: sends due scheduled digests or no-update confirmations.

## Scraper Layer

All production source adapters implement the `ScraperAdapter` protocol in
`scrapers/base.py`:

- `source_kind` identifies the adapter.
- `fetch_listings(ScrapeRequest)` returns `ListingCandidate` rows.

Adapters use configured user agent, timeout, and minimum request interval. Tests
use saved fixtures or mocked `httpx` transports.

## Persistence Layer

`init_database` creates tables with SQLAlchemy metadata. There is no migration
framework. The only compatibility shim currently adds `watches.thread_id` to
older local SQLite databases if missing.

Repositories are grouped in one module:

- `UserRepository`.
- `WatchRepository`.
- `SourceRepository`.
- `ListingRepository`.
- `ScrapeAttemptRepository`.
- `SourceTestAttemptRepository`.

## Scheduler Flow

APScheduler registers two jobs:

- `collect_listings`, every `SCRAPE_INTERVAL_MINUTES`.
- `send_due_digests`, every minute.

The digest poll interval setting exists in config, but the current scheduler job
uses a fixed one-minute interval.

## Configuration

Settings come from environment variables or `.env`:

- `DISCORD_BOT_TOKEN`.
- `DISCORD_GUILD_ID`.
- `DATABASE_URL`.
- `DEFAULT_TIMEZONE`.
- `DEFAULT_CURRENCY`.
- `DEFAULT_DISTANCE_UNIT`.
- `USD_TO_AUD_RATE`.
- `SCRAPE_INTERVAL_MINUTES`.
- `DIGEST_POLL_INTERVAL_MINUTES`.
- `SCRAPER_USER_AGENT`.
- `SCRAPER_TIMEOUT_SECONDS`.
- `SCRAPER_MIN_INTERVAL_SECONDS`.
- `LOG_LEVEL`.

Container deployment overrides `DATABASE_URL` to
`sqlite:////data/car_watch_bot.sqlite3`.
