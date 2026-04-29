# Product Requirements

## Purpose

V8Bot is a standalone Discord bot for watching car listings and delivering scheduled digests. Users define searches with included keywords, excluded keywords, preferred currency, distance unit, sources, and notification time. The bot checks configured sources during the day, stores matching listings silently, deduplicates them, and sends new results only in the user's scheduled Discord digest.

## Target Users

- Car buyers who repeatedly check multiple listing sites.
- Discord server members who want listing alerts in a predictable daily digest.
- Power users who want custom website sources tested before being added to a watch.

## MVP Scope

- Standalone Discord bot built with Python 3.11+ and `discord.py`.
- Slash commands for creating, viewing, modifying, and removing watches.
- Slash commands for adding, viewing, testing, and removing sources.
- SQLite persistence through SQLAlchemy.
- APScheduler jobs for periodic source checks and scheduled digests.
- Pydantic models for configuration, parsed listing payloads, and service boundaries.
- Mock scraper adapter that returns deterministic sample listings.
- Scraper adapter interface designed for future real website adapters.
- Listing deduplication by source, external listing id when available, URL, and normalized listing fingerprint.
- Silent listing collection during the day.
- Scheduled digests only; no immediate listing alerts in MVP.
- Price conversion to each watch's preferred currency.
- Mileage display defaults to kilometres.
- Every listing shown in a digest includes a link.

## Explicit Non-MVP

- Real production website scraping.
- Facebook Marketplace support.
- Browser automation.
- Image processing.
- User-facing website or dashboard.
- Real-time alerts outside scheduled digests.
- Machine-learning ranking or recommendation.
- Payment, subscriptions, or multi-tenant SaaS management.
- Reusable bot plugin architecture.

## Product Behaviours

### Watches

A watch describes what a user wants to find:

- Name.
- Included keywords.
- Excluded keywords.
- Preferred currency.
- Distance unit, defaulting to kilometres.
- Notification time.
- One or more enabled sources.
- Discord delivery target, initially the channel where the watch is created unless changed by command.

### Sources

A source describes where listings may come from:

- Built-in mock source for MVP development and tests.
- Custom website source records that can be added by users, but only exercised through source test behaviour in MVP.
- Source enablement per watch.
- Custom website source tests may fetch and inspect a page, but they must not create listings or participate in scheduled collection in v1.

### Collection

The bot periodically checks active watches and their enabled sources. Listings are filtered against watch keywords, normalized, deduplicated, converted into the user's preferred display units, and stored for the next digest.

MVP scheduled collection must only use sources backed by a scraper adapter, initially the built-in mock source. User-owned custom website sources are testable records, not production scrape sources.

### Digests

At the configured notification time, the bot sends a Discord digest containing new listings collected since the previous digest for that watch. After a successful send, those listing deliveries are marked as sent so they are not repeated in future digests.

## Success Criteria

- A user can create a watch from Discord slash commands.
- Mock listings matching the watch are stored without immediate notification.
- A scheduled digest posts unsent matching listings at the configured time.
- Duplicate mock listings are not repeatedly delivered.
- Prices are displayed in the watch's preferred currency.
- Mileage displays in kilometres by default.
- A source test command reports whether a custom source appears structurally usable without adding real scraping.
- Failed scheduled scrape attempts are recorded for diagnostics without notifying users.

## Risks

- Real website terms, anti-bot systems, and page changes will affect future scraping design.
- Exchange rate accuracy depends on the selected rate provider or static MVP rates.
- Discord interaction timeouts require commands to defer responses for longer operations.
- Time zone handling must be explicit to avoid sending digests at surprising times.
