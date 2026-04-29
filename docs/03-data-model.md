# Data Model

## Goals

The data model must support Discord-owned MVP usage while keeping enough separation for a future website. It should track users, watches, sources, listings, and delivery state without coupling all business logic to Discord commands.

## Entities

### User

Represents a person using the bot.

Fields:

- `id`: internal primary key.
- `discord_user_id`: Discord user id, required for MVP Discord users and nullable later for website-only users.
- `created_at`.
- `updated_at`.

Future fields:

- Website account id.
- Email.
- Preferences shared across watches.

### Watch

Represents a saved car search.

Fields:

- `id`: internal primary key.
- `user_id`: owner.
- `guild_id`: Discord guild id, nullable for future direct-message or website usage.
- `channel_id`: Discord channel for digest delivery.
- `name`.
- `included_keywords`: normalized list stored as JSON.
- `excluded_keywords`: normalized list stored as JSON.
- `preferred_currency`: ISO-style currency code, such as `AUD`, `USD`, `NZD`.
- `distance_unit`: `km` or `mi`, default `km`.
- `notification_time`: local time of day.
- `timezone`: IANA timezone, default from config.
- `criteria_version`: integer incremented when matching criteria or enabled source set changes.
- `is_active`.
- `deactivated_at`: nullable.
- `last_digest_sent_at`.
- `created_at`.
- `updated_at`.

Rules:

- A watch must have at least one included keyword.
- Excluded keywords are optional.
- Notification time is required.
- Distance unit defaults to kilometres.

### Source

Represents a listing source known to the bot.

Fields:

- `id`: internal primary key.
- `owner_user_id`: nullable; null means built-in source.
- `name`.
- `kind`: `mock`, `custom_website`, or future adapter kinds.
- `base_url`.
- `config`: JSON for source-specific metadata.
- `is_active`.
- `deactivated_at`: nullable.
- `last_tested_at`: nullable.
- `last_test_status`: nullable `passed`, `warning`, or `failed`.
- `created_at`.
- `updated_at`.

MVP rules:

- Built-in mock source is enabled for development and tests.
- Custom website sources can be stored and tested.
- Custom website sources must not perform production scraping in v1.
- Facebook Marketplace sources are rejected in v1.
- User-owned sources can only be attached to watches owned by the same user. Built-in sources can be attached to any user's watch.

### WatchSource

Join table for enabled sources on a watch.

Fields:

- `id`.
- `watch_id`.
- `source_id`.
- `is_enabled`.
- `disabled_at`: nullable.
- `created_at`.
- `updated_at`.

Rules:

- A watch can use many sources.
- A source can belong to many watches.
- A disabled source remains associated for future re-enable workflows.

### Listing

Represents a normalized listing discovered from a source.

Fields:

- `id`.
- `source_id`.
- `external_id`: nullable source-provided id.
- `url`.
- `title`.
- `description`: nullable.
- `price_amount`: nullable decimal.
- `price_currency`: nullable currency code.
- `mileage_value`: nullable integer.
- `mileage_unit`: nullable `km` or `mi`.
- `location_text`: nullable.
- `image_url`: nullable.
- `seller_name`: nullable.
- `listed_at`: nullable.
- `first_seen_at`.
- `last_seen_at`.
- `content_hash`: normalized fingerprint.
- `raw_payload`: JSON for debugging.

Rules:

- URL is required.
- Each digest item must include a link.
- Deduplication should prefer `(source_id, external_id)` when available, then canonical URL, then content hash.

### WatchListing

Represents a listing matched to a watch.

Fields:

- `id`.
- `watch_id`.
- `listing_id`.
- `matched_at`.
- `watch_criteria_version`: criteria version used when the listing matched.
- `status`: `pending_digest`, `sent`, `dismissed`.
- `sent_at`: nullable.
- `digest_batch_id`: nullable.

Rules:

- A listing can match multiple watches.
- A listing should be sent at most once per watch unless explicitly reset.
- If matching criteria change, the watch's `criteria_version` is incremented. Digest selection should only include pending rows for the current criteria version, or explicitly revalidate older pending rows before sending.

### DigestBatch

Represents one digest send attempt.

Fields:

- `id`.
- `watch_id`.
- `scheduled_for`.
- `sent_at`: nullable.
- `status`: `pending`, `sent`, `failed`, `empty`.
- `listing_count`.
- `discord_message_id`: nullable.
- `error_message`: nullable.

Rules:

- Empty digests may be recorded without sending a Discord message, depending on product choice.
- Failed digests should leave listings in `pending_digest` unless the send partially succeeded.

### ScrapeAttempt

Represents one scheduled collection attempt for a source and watch.

Fields:

- `id`.
- `watch_id`.
- `source_id`.
- `started_at`.
- `finished_at`: nullable.
- `status`: `success`, `failed`, or `skipped`.
- `adapter_kind`.
- `listings_seen`.
- `listings_matched`.
- `listings_created`.
- `error_message`: nullable.

Rules:

- Failed scrape attempts are recorded silently and do not notify users in MVP.
- Custom website sources without a production adapter should be recorded as `skipped` only if the scheduler evaluates them; preferably the scheduler should ignore non-adapter sources.
- Attempts provide diagnostics for admins and future dashboards.

### SourceTestAttempt

Represents one user-triggered custom source test.

Fields:

- `id`.
- `source_id`: nullable when testing a URL before saving it.
- `user_id`.
- `url`.
- `started_at`.
- `finished_at`: nullable.
- `status`: `passed`, `warning`, or `failed`.
- `notes`: JSON or text summary.
- `detected_links`: JSON list of sample links.
- `error_message`: nullable.

Rules:

- Source tests never create `Listing` or `WatchListing` records.
- Source tests may update `Source.last_tested_at` and `Source.last_test_status`.

## Pydantic Boundary Models

Suggested models:

- `WatchCreate`.
- `WatchUpdate`.
- `WatchView`.
- `SourceCreate`.
- `SourceTestResult`.
- `ScrapeAttemptView`.
- `SourceTestAttemptView`.
- `ListingCandidate`.
- `NormalizedListing`.
- `DigestListing`.
- `DigestPayload`.

Use Pydantic models at service boundaries and command presenters. SQLAlchemy models should remain persistence concerns.

## Indexes and Constraints

Recommended constraints:

- Unique `users.discord_user_id` when not null.
- Unique source name per owner for user-owned sources.
- Unique `(source_id, external_id)` when `external_id` is not null.
- Unique `(source_id, url)`.
- Unique `(watch_id, listing_id)` for watch matches.
- Unique `(watch_id, source_id)` for watch-source associations.

Recommended indexes:

- `watches.user_id`.
- `watches.is_active`.
- `watch_listings.watch_id, status`.
- `listings.source_id`.
- `listings.first_seen_at`.
- `digest_batches.watch_id, scheduled_for`.
- `scrape_attempts.watch_id, source_id, started_at`.
- `source_test_attempts.user_id, started_at`.
