# Data Model

## Overview

The current schema is defined in `src/car_watch_bot/db/models.py` and created by
`init_database`. It is a local SQLite-friendly prototype schema with no migration
framework.

## User

Table: `users`.

Fields:

- `id`: primary key.
- `discord_user_id`: required unique Discord user id string.
- `created_at`.
- `updated_at`.

Rules:

- Users are created idempotently by Discord id.
- Website-only users are not implemented.

## Watch

Table: `watches`.

Fields:

- `id`: primary key.
- `user_id`: owner foreign key.
- `guild_id`: Discord guild id, nullable.
- `channel_id`: Discord channel id, nullable.
- `thread_id`: resolved per-watch Discord thread id, nullable.
- `starred_thread_id`: resolved per-watch starred shortlist Discord thread id,
  nullable.
- `name`: currently set from the car query.
- `query`: car query used by scoring.
- `included_keywords`: JSON list.
- `excluded_keywords`: JSON list.
- `preferred_currency`: default `AUD`.
- `distance_unit`: `km` or `mi`, default `km`.
- `notification_time`: local time of day.
- `timezone`: default `Australia/Sydney`.
- `criteria_version`: starts at `1`.
- `is_active`.
- `deactivated_at`.
- `last_digest_sent_at`.
- `created_at`.
- `updated_at`.

Rules:

- Watch creation requires a non-empty car query and at least one included
  keyword.
- Keyword and source association changes increment `criteria_version`.
- Watch operations are scoped to the Discord owner.
- Digest delivery requires `channel_id`; thread id is resolved and persisted
  after the first send.

## Source

Table: `sources`.

Fields:

- `id`: primary key.
- `owner_user_id`: nullable; null can represent built-in/global sources.
- `name`.
- `kind`: source adapter kind.
- `base_url`.
- `config_json`: JSON metadata field.
- `is_active`.
- `deactivated_at`.
- `last_tested_at`.
- `last_test_status`.
- `created_at`.
- `updated_at`.

Constraints:

- Unique `(owner_user_id, name)`.

Current source kinds:

- `mock`.
- `autotempest`.
- `cars_on_line`.
- `corvette_magazine`.
- `vettefinders`.
- `custom_website` for unsupported domains in tests or legacy data.

Runtime source addition rejects unregistered source kinds when the app is wired
through `main.py`.

## WatchSource

Table: `watch_sources`.

Fields:

- `id`: primary key.
- `watch_id`.
- `source_id`.
- `is_enabled`.
- `disabled_at`.
- `created_at`.
- `updated_at`.

Constraints:

- Unique `(watch_id, source_id)`.

Rules:

- Adding an existing disabled association re-enables it.
- Removing a source from a watch disables the association rather than deleting
  the source row.
- Add/remove operations increment the watch criteria version.

## Listing

Table: `listings`.

Fields:

- `id`: primary key.
- `source_id`.
- `external_id`: nullable source-provided id.
- `url`: required listing URL.
- `title`.
- `description`.
- `price_amount`.
- `price_currency`.
- `converted_price_amount`.
- `converted_price_currency`.
- `mileage_value`.
- `mileage_unit`.
- `converted_mileage_value`.
- `converted_mileage_unit`.
- `location_text`.
- `score`.
- `score_reasons`: JSON list.
- `content_hash`.
- `raw_payload`: JSON metadata from the scraper.
- `first_seen_at`.
- `last_seen_at`.

Constraints:

- Unique `(source_id, url)`.
- Unique `(source_id, external_id)`.

Current dedupe behavior:

- Repository lookup and upsert are URL-first.
- `external_id` uniqueness is present as a database constraint.
- `content_hash` is stored but not currently used as the primary upsert lookup.
- Rediscovered rows are refreshed with latest listing fields, score, conversion,
  raw payload, and `last_seen_at`.
- New and refreshed rows store V8Bot namespaced price snapshots in `raw_payload`
  when a complete listing price is available. This supports honest price-change
  display without adding dedicated price history tables.

## WatchListing

Table: `watch_listings`.

Fields:

- `id`: primary key.
- `watch_id`.
- `listing_id`.
- `matched_at`.
- `watch_criteria_version`.
- `status`: currently `pending_digest`, `sent`, `excluded`, `starred`, or
  `inactive`. Older local rows may still contain legacy action states such as
  `saved`, `contacted`, `dismissed`, or `not_relevant`.
- `sent_at`.

Constraints:

- Unique `(watch_id, listing_id)`.

Rules:

- One listing can match many watches.
- A watch-listing pair is only created once.
- Sent listings are not re-posted by scheduled digests.
- Starred listings remain visible in listing history, but are not pending
  digest rows.
- Unstarred listings move back to `sent` history so they remain visible without
  returning to pending digest output.
- Inactive listings are hidden from visible listing history and are not pending
  digest rows.
- Inactive listings are not reactivated by future scrapes for the same watch.
- Listings rejected by updated exclusions can be marked `excluded`.
- If an excluded listing later matches again, it can be moved back to
  `pending_digest`.

## ScrapeAttempt

Table: `scrape_attempts`.

Fields:

- `id`: primary key.
- `watch_id`.
- `source_id`.
- `started_at`.
- `finished_at`.
- `status`: `success` or `failed` in the current service path.
- `adapter_kind`.
- `listings_seen`.
- `listings_matched`.
- `listings_created`.
- `error_message`.

Rules:

- Successful adapter calls record counts.
- Adapter exceptions record failed attempts and do not crash the scrape cycle.
- Sources without registered adapters are skipped before adapter invocation in
  `ListingService.scrape_watch_now`; that path returns warnings but does not
  create a skipped attempt row.

## SourceTestAttempt

Table: `source_test_attempts`.

Fields:

- `id`: primary key.
- `source_id`: nullable.
- `user_id`.
- `url`.
- `started_at`.
- `finished_at`.
- `status`: `passed`, `warning`, or `failed`.
- `notes`: JSON list of warnings.
- `detected_links`: JSON list, currently stored as an empty list by the service.
- `error_message`.

Rules:

- Source tests never create listings.
- Add-source source tests are recorded against the created source when accepted.
- Rejected add-source attempts are recorded without a source id when validation
  reaches the source-test phase.
- `/watch_source_test` records diagnostics for the user even when the URL cannot
  be attached as a production source.

## Not Implemented In The Current Schema

- There is no `digest_batches` table.
- Listing image URL, seller name, and listed-at fields do not have dedicated
  columns. Scrapers may preserve seller/image metadata in `raw_payload` for
  digest presentation.
- User email, website account linkage, and global preferences are not
  implemented.
- Database migrations are not implemented.
