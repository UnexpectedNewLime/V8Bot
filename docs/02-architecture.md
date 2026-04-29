# Architecture

## Overview

V8Bot should be built as a standalone Discord bot with modular core services. Discord-specific command handlers should be thin adapters over reusable application services so a future website can reuse watch management, source management, scraping orchestration, deduplication, price conversion, and digest generation.

## Technology Stack

- Python 3.11+
- `discord.py` for bot runtime and slash commands
- SQLAlchemy for ORM and database access
- SQLite for MVP persistence
- APScheduler for scrape and digest schedules
- Pydantic for settings and boundary models
- `httpx` and BeautifulSoup for MVP source testing and future scraper implementations
- pytest for automated tests

## Proposed Folder Structure

```text
v8bot/
  __init__.py
  main.py
  config.py
  logging.py

  bot/
    __init__.py
    client.py
    commands/
      __init__.py
      watches.py
      sources.py
      admin.py
    presenters/
      __init__.py
      digest_presenter.py
      command_presenter.py

  core/
    __init__.py
    models.py
    errors.py
    services/
      __init__.py
      watch_service.py
      source_service.py
      scrape_service.py
      digest_service.py
      currency_service.py
      unit_service.py
      dedupe_service.py
      source_test_service.py

  db/
    __init__.py
    engine.py
    session.py
    models.py
    repositories/
      __init__.py
      watches.py
      sources.py
      listings.py
      deliveries.py
      scrape_attempts.py
      source_test_attempts.py

  scrapers/
    __init__.py
    base.py
    mock.py
    source_tester.py
    normalization.py

  scheduler/
    __init__.py
    jobs.py
    setup.py

tests/
  unit/
  integration/
  fixtures/

docs/
```

## Layering

### Discord Layer

The Discord layer owns:

- Bot startup and login.
- Slash command registration.
- Interaction deferral and response formatting.
- Discord channel/user/guild identifiers.
- Embed or message presentation.

It should not own scraping, database rules, deduplication, currency conversion, or digest business logic.

### Application/Core Layer

The core layer owns:

- Watch lifecycle.
- Source lifecycle.
- Scrape orchestration.
- Listing filtering and deduplication.
- Digest selection and delivery state changes.
- Currency and unit normalization rules.

Core services should receive dependencies explicitly, such as repositories, scraper registry, currency converter, and clock.

### Persistence Layer

The persistence layer owns SQLAlchemy models, sessions, repositories, and database transaction boundaries. Repositories should expose intention-revealing methods rather than leaking query details into command handlers.

### Scraper Layer

The scraper layer owns source adapters. MVP implementation should include only mock scraping and a source test utility for validating custom website inputs. Real scraping should be added later behind the same adapter interface.

MVP source tests may use `httpx` and BeautifulSoup to inspect a submitted custom website URL, but this is not the same as production scraping. Source tests return diagnostics and optional detected links; they do not create listings, schedule collection, or register a custom scraper adapter.

### Scheduler Layer

The scheduler layer owns recurring jobs:

- Periodic scrape collection.
- Digest delivery checks.
- Optional cleanup jobs for stale records.

Jobs should call core services rather than performing business logic directly.

## Runtime Flow

1. Bot starts and loads settings.
2. Database engine and sessions are configured.
3. Core services and scraper registry are assembled.
4. Discord commands are registered.
5. APScheduler starts periodic scrape and digest jobs.
6. Scrape jobs select active watches and enabled sources that have a registered adapter.
7. Scrape jobs record attempt status, store matching listings silently, and leave failures available for diagnostics.
8. Digest jobs send due watch digests and mark deliveries as sent.

## Multi-User and Ownership Rules

- Every watch belongs to exactly one user.
- A user can own many watches.
- A watch can have many enabled sources through `WatchSource`.
- Built-in sources are globally available.
- User-owned custom sources are visible to their owner and can be attached to that owner's watches.
- Commands must scope watch and source selectors by the interacting Discord user unless an admin command explicitly opts into a broader scope.
- Digest delivery uses the watch's stored Discord guild and channel ids, not the current command interaction.

## Configuration

Use a Pydantic settings model for:

- Discord bot token.
- SQLite database URL.
- Default timezone.
- Default currency.
- Default distance unit.
- Scrape interval.
- Digest polling interval.
- Mock scraper settings.
- Logging level.

Secrets should come from environment variables or a local ignored `.env` file.

## Future Website Reuse

To keep services reusable later:

- Keep Discord IDs as fields on watch delivery settings, not as global assumptions.
- Avoid passing Discord interaction objects into core services.
- Return Pydantic DTOs or domain objects from services.
- Keep presentation formatting outside core services.
- Keep authentication and user ownership concepts explicit in the data model.
- Keep source, watch, and digest services callable without Discord imports.
