# Implementation Plan

## Milestone 1: Project Skeleton

Goals:

- Establish Python 3.11+ package layout.
- Add dependency management.
- Add linting and formatting decisions.
- Add settings model.
- Add bot entrypoint.

Deliverables:

- `v8bot/` package.
- `tests/` package.
- Basic config loading.
- Minimal startup path that can run without connecting to Discord in tests.

## Milestone 2: Database and Repositories

Goals:

- Define SQLAlchemy models.
- Configure SQLite engine and sessions.
- Implement repositories for users, watches, sources, watch-source links, listings, watch listings, digest batches, scrape attempts, and source test attempts.

Deliverables:

- Database initialization.
- Repository tests using temporary SQLite databases.
- Seed or startup creation for built-in mock source.
- Persistence for failed scrape attempts and source test attempts.

## Milestone 3: Core Watch and Source Services

Goals:

- Implement watch create/list/show/edit/deactivate flows.
- Implement source add/list/test/deactivate flows.
- Enforce MVP source restrictions, including no Facebook Marketplace in v1.
- Keep user-owned source tests separate from scheduled production scraping.

Deliverables:

- Pydantic request and response models.
- Unit tests for validation and ownership rules.
- Source test service returning structured results.
- Criteria version updates when watch matching rules or enabled source set changes.

## Milestone 4: Mock Scraping and Deduplication

Goals:

- Define scraper adapter interface.
- Implement deterministic mock scraper.
- Normalize listing candidates.
- Match listings against watch keywords.
- Deduplicate listings globally and per watch.
- Record scrape attempt status for successes, failures, and skipped non-adapter sources when applicable.

Deliverables:

- `ScraperAdapter` protocol or abstract base class.
- `MockScraperAdapter`.
- Dedupe service.
- Tests for keyword filtering, exclusions, URL dedupe, external id dedupe, and content hash dedupe.
- Tests that failed scraper calls create `ScrapeAttempt` records without notifying users.

## Milestone 5: Currency and Unit Display

Goals:

- Convert listing prices to the watch's preferred currency.
- Convert mileage to the watch's distance unit.
- Default mileage display to kilometres.

Deliverables:

- Currency service with MVP static rates or injectable provider.
- Unit conversion service.
- Tests for price and mileage display.

## Milestone 6: Digest Service

Goals:

- Select pending listings for each due watch.
- Build digest payloads.
- Mark deliveries as sent after successful Discord send.
- Preserve pending status after failed sends.

Deliverables:

- Digest payload models.
- Digest service tests.
- Empty digest handling policy.

## Milestone 7: Scheduler

Goals:

- Configure APScheduler.
- Add periodic scrape job.
- Add digest due-check job.

Deliverables:

- Scheduler setup module.
- Job functions that call core services.
- Tests with a fake clock where practical.

## Milestone 8: Discord Slash Commands

Goals:

- Register watch and source commands.
- Use ephemeral responses for configuration.
- Render scheduled digest messages.

Deliverables:

- Command modules under `v8bot/bot/commands/`.
- Presenter helpers.
- Interaction tests or service-level command handler tests where feasible.

## Milestone 9: End-to-End MVP Hardening

Goals:

- Run bot locally against a test Discord server.
- Verify watch creation, mock scrape collection, and scheduled digest delivery.
- Confirm no immediate listing alerts occur.
- Confirm custom source tests do not create listings.

Deliverables:

- Manual QA checklist.
- Updated README with setup and run instructions.
- Known limitations documented.

## Implementation Order

Recommended order:

1. Skeleton and settings.
2. Database models and repositories.
3. Pydantic DTOs and core services.
4. Mock scraper and dedupe.
5. Digest service.
6. Scheduler.
7. Discord command layer.
8. Testing and documentation updates.

## Definition of Done for MVP

- Tests pass with pytest.
- Bot can start with a local SQLite database.
- User can manage watches and sources through slash commands.
- Mock scraper stores matching listings silently.
- Digest sends only at the configured notification time.
- Listings are deduped per watch.
- Digest listings include links.
- Facebook Marketplace is blocked in v1.
