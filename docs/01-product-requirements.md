# Product Requirements

## Purpose

V8Bot is a purpose-built Discord bot for watching car listings. Users create a
watch with a car query, included keywords, excluded keywords, preferred currency,
distance unit, source URLs, and a notification time. The bot stores matching
listings, deduplicates them per source and watch, and posts listing embeds to a
watch-specific Discord thread.

## Target Users

- Discord server members repeatedly checking car listings.
- Car buyers who want a predictable watch thread instead of scattered manual
  links.
- Power users who want to test known source URLs before attaching them to a
  watch.

## Current Scope

- Standalone Python 3.11+ Discord bot using `discord.py`.
- SQLite persistence through SQLAlchemy.
- APScheduler jobs for periodic scrape collection and due digest checks.
- Service-layer watch, source, listing, scrape, digest, and notification flows.
- Deterministic mock scraper for tests and local service checks.
- Real registered adapters for:
  - AutoTempest.
  - Cars On Line.
  - Corvette Magazine classifieds.
  - VetteFinders.
- Diagnostic testing for unsupported URLs.
- User-triggered immediate scraping through `/watch_scrape_now` and the
  `scrape_now` option on `/watch_add`.
- Scheduled digests at each watch's notification time.
- Per-watch public Discord threads for listing embeds and digest messages.
- Static USD to AUD conversion through `USD_TO_AUD_RATE`.
- Mileage display in the watch's preferred distance unit, defaulting to
  kilometres.

## Explicitly Out Of Scope

- Facebook Marketplace support.
- Browser automation or challenge bypassing.
- Direct Cars.com, Gateway Classic Cars, or Streetside Classics scraping while
  polite requests receive challenge responses.
- Carsales scraping until a concrete target URL and permission posture exist.
- A user-facing web dashboard.
- Payment, subscription, or SaaS management features.
- Reusable plugin architecture.
- Machine-learning ranking.

## Watch Behavior

A watch currently stores:

- Discord owner.
- Discord guild, channel, and resolved thread id.
- Car query.
- Included keywords.
- Excluded keywords.
- Preferred currency.
- Distance unit.
- Notification time and timezone.
- Criteria version and active state.

Material keyword or source changes increment `criteria_version`. Watch commands
scope operations to the interacting Discord user.

## Source Behavior

Users attach sources to watches with `/watch_source_add` or during
`/watch_add`. The URL host determines the source kind for known adapters:

- `autotempest.com` -> `autotempest`.
- `cars-on-line.com` -> `cars_on_line`.
- `corvette-mag.com` -> `corvette_magazine`.
- `vettefinders.com` -> `vettefinders`.
- Other domains -> `custom_website`.

Runtime source addition is configured with `allow_unregistered_sources=False`,
so `custom_website` URLs are rejected for attachment unless a test harness
injects a custom adapter. `/watch_source_test` can still run a diagnostic fetch
for unsupported domains and report sampled links and warnings without enabling
scheduled scraping.

Facebook URLs are rejected.

## Listing And Notification Behavior

Scheduled scrape jobs collect listings from registered adapters and store
matching rows silently. Scheduled digest jobs later read stored pending listings
and post them to the watch thread when the watch's local notification time is
due. Empty due digests post a no-update confirmation and update the watch's last
digest timestamp.

Manual user-triggered scraping is intentionally more immediate:

- `/watch_add` defaults `scrape_now` to true when source URLs are supplied.
- `/watch_scrape_now` scrapes one owned watch immediately.
- New listings from those manual flows are posted as embeds to the watch thread
  and then marked sent.
- `/watch_listings` posts visible listing history, including sent listings.

## Success Criteria

- The bot starts from `PYTHONPATH=src python -m car_watch_bot.main` with a valid
  Discord token.
- Slash commands sync in a configured development guild.
- A user can create, list, update, and deactivate watches.
- A user can add, list, test, and remove watch sources.
- Known source URLs are classified into the registered source kinds.
- Unsupported source tests return structured diagnostics without enabling
  production scraping.
- Scrape runs deduplicate listings and avoid duplicate pending deliveries.
- Scheduled digests only send due watches once per local notification minute.
- Per-watch Discord threads are created, reused, and persisted.
- Tests pass without Discord credentials or live network calls.
