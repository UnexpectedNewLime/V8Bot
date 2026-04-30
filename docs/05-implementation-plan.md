# Implementation Plan

## Current Implementation Status

The repository has passed the original skeleton phase. The current codebase
contains:

- Python package, configuration, logging, and bot entrypoint.
- SQLAlchemy models and repositories.
- Watch, source, listing, scrape, digest, and notification services.
- Deterministic mock scraper.
- Registered real adapters for AutoTempest, Cars On Line, Corvette Magazine, and
  VetteFinders.
- Diagnostic scraper for unsupported source tests.
- Flat Discord slash command surface.
- Per-watch Discord thread routing.
- APScheduler scrape and digest jobs.
- Local scripts for service-layer and adapter-level checks.
- Unit and integration-style tests with in-memory SQLite and saved HTML
  fixtures.
- Podman-first container setup with Docker override support.

## Completed Milestones

### Project Skeleton

Completed:

- `car_watch_bot` package under `src/`.
- `pyproject.toml` and `requirements.txt`.
- Pydantic settings in `config.py`.
- Runtime entrypoint in `main.py`.

### Database And Repositories

Completed:

- SQLAlchemy table models for users, watches, sources, watch-source links,
  listings, watch listings, scrape attempts, and source test attempts.
- Repository layer in `db/repositories.py`.
- In-memory SQLite tests.
- Compatibility helper for adding `watches.thread_id` to old local databases.

Not implemented:

- General migration framework.
- Digest batch persistence.

### Core Services

Completed:

- Watch create/list/deactivate and preference updates.
- Keyword and exclusion updates.
- Source add/list/remove/test flows.
- Source name generation and reuse.
- Manual scrape-now flow.
- Digest payload formatting and sent-state updates.
- Scheduled notification service.

### Scraping

Completed:

- `ScraperAdapter` protocol.
- Mock scraper.
- AutoTempest static/queue result parsing.
- Cars On Line static card parsing.
- Corvette Magazine classified card parsing.
- VetteFinders summary row parsing.
- Unsupported-domain diagnostics.
- Saved fixture parser tests.

Still limited:

- Adapters intentionally use polite static HTTP only.
- Challenge-heavy direct marketplace sites are not registered.
- Carsales is pending a concrete URL and policy decision.

### Discord Commands

Completed:

- Watch creation, listing, removal, keyword edits, preference updates.
- Source add/list/remove/test.
- Manual scrape and listing posting.
- Ephemeral command summaries.
- Public per-watch listing threads.

Current command structure is flat underscore commands, not nested groups.

### Scheduler

Completed:

- `collect_listings` interval job.
- `send_due_digests` one-minute interval job.
- Scheduler lifecycle tied to the Discord client setup/close path.

Known mismatch:

- `DIGEST_POLL_INTERVAL_MINUTES` exists in settings, but `create_scheduler`
  currently schedules digest checks every minute.

## Recommended Next Work

1. Decide whether digest batches are still needed. If yes, add the table,
   repository methods, service integration, and tests. If no, keep docs and
   product language centered on `watch_listings` and `last_digest_sent_at`.
2. Add a migration approach before making more schema changes.
3. Reconcile `/watch_listings` naming/description with its current behavior of
   showing visible listing history, not only pending listings.
4. Decide whether `DIGEST_POLL_INTERVAL_MINUTES` should control the scheduler or
   be removed from config.
5. Expand currency conversion beyond USD to AUD only if product scope requires
   it.
6. Add a source adapter only when polite HTTP access and parser fixtures are
   available.
7. Clean up legacy README notes that are outside `docs/` when making a README
   pass.

## Definition Of Done For New Changes

- Existing tests pass with `pytest`.
- For code changes, `python -m compileall src tests scripts` passes.
- New behavior has focused tests.
- Docs and README stay aligned when commands, config, schema, or supported
  source kinds change.
- No secrets, local `.codex/` context, SQLite files, or runtime Docker overrides
  are committed.
