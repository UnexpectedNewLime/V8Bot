# Read This First

## Purpose

This repository is still in planning mode. Future agents should read these docs before writing application code and should keep the MVP small: a standalone Discord bot, mock scheduled scraping only, custom source tests only, and scheduled digests only.

## Canonical Implementation Order

1. Read all files in `docs/` before changing code.
2. Create the project skeleton and configuration.
3. Build the database models and repositories.
4. Build core services for users, watches, sources, source tests, scraping, dedupe, currency, units, and digests.
5. Add the mock scraper adapter and scraper registry.
6. Add APScheduler jobs for collection and digest checks.
7. Add Discord slash commands as thin adapters over core services.
8. Add tests alongside each milestone.
9. Update docs and README after implementation decisions become concrete.

## Non-Negotiable MVP Rules

- Do not implement real website scraping yet.
- Do not implement Facebook Marketplace support in v1.
- Do not send immediate listing alerts.
- Do not make this a reusable plugin.
- Do not put Discord interaction objects inside core services.
- Do not let custom website sources participate in scheduled scraping until a real adapter exists.
- Do not create listings from source tests.

## Key Architecture Constraints

- Multiple Discord users must be supported from the start.
- Each user can have multiple watches.
- Each watch can have multiple sources through `WatchSource`.
- Built-in sources can be shared globally.
- User-owned custom sources must be scoped by owner.
- Scheduled digests are per watch and delivered to the watch's stored Discord channel.
- Core services should be reusable by a future web dashboard.

## Data Model Watchpoints

The implementation should include records for:

- Pending and sent watch listings.
- Digest batches.
- Scrape attempts, including failures.
- Source test attempts.
- Source activation and deactivation.
- Watch criteria versioning so material watch edits do not accidentally send stale pending matches.

## Recommended First Coding Pass

Start with boring foundations:

- `pyproject.toml` and dependencies.
- `v8bot/config.py` using Pydantic settings.
- SQLAlchemy engine/session setup.
- SQLAlchemy models matching `docs/03-data-model.md`.
- Repository tests with temporary SQLite.

Delay Discord command work until the core services can be tested without Discord.

## When Docs Disagree

Treat this file and `docs/01-product-requirements.md` as product authority. Treat `docs/03-data-model.md` as persistence authority. If an implementation detail conflicts with MVP constraints, preserve the MVP constraint and update the affected doc before coding.
