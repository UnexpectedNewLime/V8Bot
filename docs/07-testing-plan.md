# Testing Plan

## Goals

Testing should prove that V8Bot can manage watches and sources, collect mock listings silently, dedupe matches, and send scheduled digests without implementing real website scraping.

Use pytest as the primary test runner.

## Test Layers

### Unit Tests

Cover pure and mostly pure logic:

- Keyword normalization.
- Included and excluded keyword filtering.
- Currency conversion.
- Mileage conversion.
- Listing normalization.
- Content hash generation.
- Deduplication decisions.
- Digest payload formatting.
- Timezone and notification-time calculations.
- Facebook Marketplace rejection.
- Criteria version changes after watch search edits or source enablement changes.

### Repository Tests

Use temporary SQLite databases to test:

- User upsert by Discord id.
- Watch create, update, list, and deactivate.
- Source create, list, and deactivate.
- Watch-source enable and disable.
- Listing upsert by external id.
- Listing upsert by URL.
- Watch listing uniqueness.
- Digest batch persistence.
- Scrape attempt persistence.
- Source test attempt persistence.

### Service Tests

Test core service behaviour with fake repositories where useful and SQLite repositories where transaction behaviour matters:

- Creating a valid watch.
- Rejecting invalid watch inputs.
- Editing only provided fields.
- Adding a custom source.
- Rejecting unsupported source URLs.
- Running a source test without creating listings.
- Recording source test attempts.
- Running mock scrape collection without sending Discord messages.
- Recording failed scrape attempts without notifying users.
- Matching listings to watches.
- Keeping duplicate listings out of pending digest rows.
- Excluding or revalidating pending matches from old watch criteria versions.
- Selecting due digests.
- Marking listings sent only after successful delivery.

### Scheduler Tests

Use fake services and controlled clocks:

- Scrape job calls scrape service on the configured interval.
- Digest job checks due watches.
- Failed job calls are logged and do not crash the scheduler.

### Discord Command Tests

Prefer testing command handlers through service boundaries and presenters:

- Slash command options map to service requests.
- Long operations defer responses.
- Configuration commands return ephemeral responses.
- Watch list and source list presenters fit Discord limits.
- Digest presenter splits messages when necessary.

Full Discord API tests should be manual for MVP unless a dedicated test harness is added.

## Fixtures

Recommended fixtures:

- Temporary SQLite database.
- SQLAlchemy session factory.
- Fake clock.
- Mock scraper adapter.
- Example users.
- Example watches.
- Example sources.
- Example listing candidates.
- Currency rate provider with fixed rates.

## Mock Scraper Test Cases

The deterministic mock scraper should support tests for:

- New listing discovery.
- Duplicate listing rediscovery.
- Multiple currencies.
- Kilometre and mile mileage values.
- Excluded keyword filtering.
- Listings with missing optional fields.
- Required URL presence.

## Source Test Cases

Source test should cover:

- Valid custom URL with listing-like HTML.
- Valid custom URL with no listing-like content.
- Invalid URL.
- Unreachable URL through mocked `httpx`.
- Timeout through mocked `httpx`.
- Facebook Marketplace URL rejected.
- Source test does not create listing records.
- Source test records an attempt and updates latest source test status.

## Digest Test Cases

Digest tests should cover:

- No pending listings.
- One pending listing.
- Multiple pending listings.
- Listings already sent are excluded.
- Digest failure leaves listings pending.
- Successful digest marks listings sent.
- Pending listings from stale watch criteria are not accidentally sent after a material watch edit.
- Price display uses preferred currency.
- Mileage display defaults to kilometres.
- Each digest listing includes a link.

## Integration Tests

MVP integration tests should run locally without network access:

- Initialize database.
- Create user, source, and watch.
- Run mock scrape collection.
- Confirm pending watch listings.
- Confirm scrape attempt record.
- Run digest service with a fake Discord sender.
- Confirm sent state and digest batch record.

## Manual QA Checklist

Before considering MVP complete:

- Bot starts locally with configured Discord token.
- Slash commands sync in a test guild.
- `/watch add` creates a watch.
- `/watch list` shows the watch.
- `/watch edit` changes notification time and currency.
- `/source add` rejects Facebook Marketplace.
- `/source test` returns a structured result.
- Mock scrape stores listings without posting to Discord.
- Digest posts at the configured time.
- Duplicate listings are not resent.
- Every digest listing contains a link.

## Test Data Safety

- Tests should not require real Discord credentials.
- Tests should not make live website requests by default.
- Tests should not depend on real exchange rates.
- Tests should clean up temporary SQLite files.
