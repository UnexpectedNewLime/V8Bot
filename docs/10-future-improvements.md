# Future Improvements

Ordered by effort. Items marked **[new-dev]** are self-contained and well-suited
for someone still getting familiar with the codebase.

---

## Easy

**[new-dev] `/watch_rename` command**
`update_watch()` already accepts a `name` field but there is no dedicated
command for it. `/watch_edit` covers it but buries it alongside a dozen other
fields. A focused `/watch_rename <watch_id> <name>` teaches the
command → service pattern without touching any other layer.

**[new-dev] `/watch_pause` and `/watch_resume` commands**
`update_watch()` supports toggling `is_active` but there is no user-facing way
to temporarily pause a watch and resume it later without losing it. Each command
is one service call with no schema changes needed.

**[new-dev] `/watch_stats` command**
Show per-watch summary stats: number of active sources, total listings found,
listings sent, last scraped timestamp, and next notify time. All data exists
across `ScrapeAttempt`, `WatchListing`, and `Watch`. Read-only — no writes.

**[new-dev] `/watch_digest_preview` command**
Run the digest build without marking listings as sent so the user can preview
what would be posted at notify time. `DigestService.build_digest()` already
returns the payload; just skip the `mark_digest_sent()` call.

**[new-dev] `/help` command**
A static embed listing command groups (watch management, keyword management,
source management, utility) with one-line descriptions. Good introduction to the
embed system in `bot/embeds.py`.

**[new-dev] `/watch_listings` copy cleanup**
`/watch_listings` now shows visible listing history, including sent rows, but
some command descriptions, headings, empty messages, helper docstrings, and docs
still say "pending listings". Reconcile the user-facing copy with the actual
behavior. This is a good first codebase-tracing task with tiny blast radius.

**[new-dev] Use `DIGEST_POLL_INTERVAL_MINUTES` in the scheduler**
`Settings` exposes `DIGEST_POLL_INTERVAL_MINUTES`, but `create_scheduler()`
currently schedules digest checks every minute. Either wire the setting through
and test it, or remove the setting and update docs/README. Wiring it through is
small, useful, and teaches config-to-runtime flow.

**[new-dev] Source failure warnings in digests**
`ScrapeAttempt` logs every success and failure. When a source has failed N
consecutive times, include a short warning line at the top of the next digest.
Purely a read-and-format task in `digest_service.py` — no schema changes.

**[new-dev] Per-source enable/disable toggle**
Users can only add or remove sources. A `/watch_source_toggle <watch_id>
<source_id>` command that flips the `WatchSource.is_enabled` flag would let
users temporarily mute a noisy source without losing the link. The column
already exists; add a small repository/service method for explicit toggle or
re-enable behavior.

**[new-dev] Use `criteria_version` to re-surface old listings**
`Watch.criteria_version` increments whenever keywords or sources change and
`WatchListing` records the version at insert time, but the code never compares
them. Add a filter in `ListingRepository.list_unnotified_for_watch()` to also
return listings whose `criteria_version` is older than the current watch
version, then wire it through the digest. No schema changes needed.

**[new-dev] `/watch_export` — CSV attachment**
Add a command that queries all visible listings for a watch and returns them as
a `.csv` file uploaded directly to Discord via `discord.File`. No schema
changes, no server needed. Good introduction to the repository → service →
command path and Discord file uploads.

**[new-dev] DM alert toggle per watch**
Add a boolean `dm_on_new_listing` column to `Watch`. When set, the scrape
service sends the watch owner a Discord DM immediately when a new listing
passes the score threshold, without waiting for the daily digest. The DM path
already exists in the Discord client; the main task is threading the setting
through `ScrapeService` and the command interface.

---

## Medium

**Command cooldowns on expensive operations**
Nothing prevents a user from hammering `/watch_scrape_now` or
`/watch_source_test` in quick succession. `discord.app_commands` exposes a
`@app_commands.checks.cooldown()` decorator. Wrap the scrape and source-test
commands with a per-user cooldown and handle the
`CommandOnCooldown` exception in the existing error path.

**Retry logic for transient HTTP failures in scrapers**
Each scraper makes a single `httpx` call with no retry on timeout or 5xx.
Adding 2–3 attempts with exponential backoff (via `tenacity` or a small manual
loop) inside the scraper base class would improve reliability against flaky
networks without touching the service or bot layers.

**Listing history UX: `/watch_history` or `/watch_listings` rename**
`/watch_listings` already includes sent listing history, but the command name
does not make that obvious. Either add `/watch_history` as a clearer alias over
the existing service path, or rename the command intentionally and update tests,
docs, and user-facing copy. This teaches the command → service → embed path
without schema changes.

**`/watch_duplicate` command**
Clone an existing watch — same query, keywords, exclusions, timezone, currency,
and notify time — into a new row with no sources attached. Useful when a user
wants to track the same car on a different set of sources. One
`WatchService.create_watch()` call seeded from `get_watch_details()`.

**Price range filter on watches**
Add optional `min_price` and `max_price` columns to `Watch`. Apply them in
`scoring.py` so listings outside the range receive a score below the threshold.
Requires a schema change, a migration, and corresponding service + command
updates.

**Mileage ceiling filter on watches**
Same pattern as price range but for a `max_mileage` column. Lets users ignore
high-mileage cars without having to add keywords.

**Year range filter on watches**
Add `min_year` / `max_year` columns to `Watch` and extract year from listing
titles or `raw_payload` during scoring. Scrapers already include year in titles;
extraction is the main design task.

**Digest pagination**
When a digest has many listings the bot posts them all at once, which can flood
a thread. Add a `page` parameter to the listing embed and split digests into
batches of N with a "page X of Y" footer. The chunking logic in `commands.py`
is a reference for splitting output.

**Source health summary command**
A `/source_health <watch_id>` command that shows, for each source, the last
scrape time, last success, consecutive failure count, and total listings found.
Read-only query over `ScrapeAttempt` rows.

**Autocomplete on watch name in addition to watch ID**
The autocomplete callbacks filter on watch ID and query text but not on the
watch name field. Including name in the match improves discoverability for users
with many watches. Change is isolated to the autocomplete helper functions in
`commands.py`.

**`/listing_exclude` command**
Let users exclude a specific listing by ID so it never appears in future digests
for that watch. `WatchListing.status` already has an `excluded` value and the
repository has `exclude_listing()`; the missing piece is a command that accepts
a listing ID and calls it. Useful when a known bad listing keeps reappearing.

**`/watch_share` — shareable config embed**
Generate a formatted embed (or a small JSON/text block) describing a watch's
query, keywords, exclusions, notify time, and currency so another user can
recreate it with `/watch_add`. No DB writes, no new columns — purely a read and
format task, but teaches the full service and embed path.

**Watch expiry date**
Add an optional `expires_at` timestamp column to `Watch`. The scheduler's
digest job already iterates active watches; extend it to deactivate any whose
`expires_at` has passed and post a notice to the watch thread. Useful for
time-boxed searches ("I'll decide in 30 days"). Requires a schema change and a
migration.

---

## Hard

**Cross-source deduplication via `external_id`**
`Listing.external_id` is populated by scrapers but the uniqueness constraint is
`(source_id, url)`. The same car appearing on AutoTempest and VetteFinders
creates two rows. True deduplication requires comparing `external_id` values
across sources, deciding which listing row wins for price history, and updating
the schema and queries. Design work is significant.

**Circuit breaker for failing sources**
Beyond warning users, automatically skip sources that have exceeded a failure
threshold and re-enable them after a success. Requires a small state machine
(or columns like `consecutive_failures`, `disabled_until`) on `Source` or
`WatchSource`, plus logic in `ScrapeService` to skip and unblock. More moving
parts than a single-layer task.

**Multiple notification times per watch**
`Watch.notification_time` is a single `TIME` column. Supporting multiple daily
notify times requires either a related `WatchNotifyTime` table or a JSON array
column, plus changes to the scheduler's due-digest check logic and the
command interface.

**Dynamic currency conversion**
`USD_TO_AUD_RATE` is a static config value. Fetching a live rate from an
exchange-rate API on a schedule and storing it avoids stale conversions. Adds
an external dependency, a new scheduled job, and a new config value for the
API key or source URL.

**New scraper: Carsales**
Carsales is the dominant Australian marketplace and would significantly improve
result coverage. The scraper protocol is documented in `06-scraper-design.md`.
AutoTempest is the best reference implementation. The main unknowns are the
search URL structure and whether the response is static HTML or requires a
JavaScript-rendered client. Validate with the diagnostic scraper first.

**Full-text search on listing history**
Allow users to search past listings with `/watch_search <query>`. SQLite has a
built-in FTS5 extension; hooking it up requires a virtual table, an insert
trigger or explicit index-update call, and a new repository query. The Discord
output path already exists via the history command above.

**Real-time listing notifications**
All delivery is currently time-gated by `notification_time`. Add an opt-in mode
where a watch posts each new matching listing to its thread the moment the
scraper finds it, rather than batching into a daily digest. Requires a new
delivery path in `ScrapeService` that bypasses `DigestService`, careful
deduplication to avoid re-posting on re-scrape, and a toggle in the watch
settings.

**Listing interest feedback loop**
Add Discord reaction listeners (👍 / 👎) to listing embeds. Record each
reaction as a `ListingFeedback` row tied to the user and listing. Feed the
aggregate signal back into `scoring.py` — positively-reacted listings from the
same source or price band get a small score boost on future scrapes. Requires a
new table, a Discord event handler, and a scoring signal that crosses the
session boundary.

---

## Web & Integrations

**`/watch_view` — static HTML file export**
Generate a self-contained HTML file (inline CSS, no external dependencies)
displaying all listings for a watch as a card grid, then upload it to Discord
via `discord.File`. Each card shows the thumbnail, title, price, mileage,
score, and a link to the original listing. No server or URL needed — the file
opens locally in a browser. A good entry point to the web section before
committing to a running server.

**Per-watch web dashboard with token URL**
Run a small read-only `aiohttp` or FastAPI server alongside the bot process.
Each watch gets a unique access token stored in the DB. `/watch_view <watch_id>`
returns an ephemeral message with a URL the user can open in a browser. The
page renders all listings in a card layout with client-side filtering by price,
mileage, score, and source, plus a price-over-time sparkline per listing.
Authentication is the token in the URL; no login system required. The server
shares the same `SessionFactory` as the bot so no data duplication is needed.
This is the largest standalone addition in this list — plan the server lifecycle
(startup, shutdown, port config) carefully before implementation.

**Per-watch RSS / Atom feed**
Expose a `/feed/<watch_token>.xml` endpoint on the same server as the dashboard.
Each new listing that passes the score threshold appears as a feed item with
title, price, mileage, location, and a link. Users can subscribe in any RSS
reader (Feedly, NetNewsWire, etc.) for passive monitoring without opening
Discord. Builds directly on top of the dashboard server infrastructure above.

**Email digest alternative**
Add an optional `notify_email` field to `Watch`. When set, the digest job sends
an HTML email via SMTP (configurable in `.env`) in addition to or instead of the
Discord thread post. The email body mirrors the digest embed: listing cards,
score reasons, and price history. Adds `aiosmtplib` as a dependency. Useful for
users who want a searchable email archive of listings.

**Outbound webhook per watch**
Add an optional `webhook_url` field to `Watch`. After each successful digest
send, POST a JSON payload to the URL containing the watch ID, query, and a list
of listing objects. Lets users pipe listing data into Zapier, Make, a personal
home server, or any HTTP listener without building a custom integration. The
payload schema should be versioned from day one.

---

## Infrastructure

**GitHub Actions CI — test and lint on every PR**
Run `pytest` and `python -m compileall src tests scripts` on pull requests
targeting `main`. Add `black --check` and `ruff` for formatting and lint
enforcement. A failing check should block merge. Reference the commands in
`CLAUDE.md` under "Verify changes".

**GitHub Actions CD — auto-deploy `main` to production runner**
On push to `main`, SSH into the host runner, pull the latest image, and restart
the service via `docker compose up -d --pull always`. Requires a GitHub
Actions secret for the host SSH key and a deploy user on the runner with
minimal permissions (restart service only).

**Dependabot for dependency updates**
Add a `.github/dependabot.yml` config to open weekly PRs for outdated packages
in `requirements.txt`. Keeps the dependency surface small and auditable without
manual tracking.

**Pre-commit hooks**
Add a `.pre-commit-config.yaml` running `black`, `ruff`, and `compileall` so
formatting issues are caught before they reach CI. Document setup in `README.md`
under dev setup.

**Coverage reporting in CI**
Extend the CI workflow to run `pytest --cov=car_watch_bot --cov-report=xml` and
upload the result to Codecov or a similar service. Add a coverage badge to
`README.md`. Useful signal for finding untested paths as the codebase grows.

**Structured log shipping**
The bot uses the standard `logging` module with `extra={}` metadata but logs
only to stdout. Add a handler that ships JSON-formatted logs to a collector
(e.g., Loki, Datadog, or a simple file sink rotated by the host). Requires a
logging config change and a new environment variable for the sink endpoint.

**Database backup job**
Add a cron job (or GitHub Actions scheduled workflow) that copies the SQLite
file to a remote location (S3, Backblaze, or a Git-tracked data repo) on a
daily schedule. Low effort but high value for a single-file database with no
replication.

**Database migration framework**
Before adding more schema-heavy features like price, mileage, year filters, or
multiple notification times, introduce a lightweight migration workflow for the
SQLite database. Alembic is the conventional SQLAlchemy option, but a smaller
repo-local migration runner could also work if the project wants to stay very
lean. Include documentation for local upgrade/rollback expectations.
