# Codex Overnight Instructions

## Current State

The project planning docs have been created.

The initial Python project scaffold has also been created from the scaffold prompt.

Before making changes, read:

- `docs/00-agent-rules.md`
- `docs/00-read-this-first.md`
- `docs/01-product-requirements.md`
- `docs/02-architecture.md`
- `docs/03-data-model.md`
- `docs/04-command-design.md`
- `docs/05-implementation-plan.md`
- `docs/06-scraper-design.md`
- `docs/07-testing-plan.md`
- `docs/08-style-guide.md`
- `docs/09-engineering-principles.md`

Follow these docs strictly.

---

# Primary Goal

Continue implementation up to a working local prototype using **mock scraping only**.

Do **not** implement real website scraping yet.

The prototype should support:

1. Database models and repositories
2. Core scoring and conversion logic
3. Mock scraper pipeline
4. Basic Discord slash command structure if time permits
5. Passing tests

---

# Hard Constraints

Do not violate these:

- Do not implement Facebook Marketplace scraping.
- Do not implement live scraping yet.
- Do not add a web dashboard.
- Do not bypass the service layer.
- Do not put business logic in Discord command handlers.
- Do not let scrapers write directly to the database.
- Do not send notifications immediately after scraping.
- Do not store secrets in code.
- Do not make live network calls in tests.

---

# Implementation Order

## Phase 1 — Database + Repositories

Implement SQLAlchemy models for:

- User
- Watch
- Source
- Listing
- ScrapeRun or SourceTestResult, if already planned in docs

Implement repository functions for:

- create/get user by Discord ID
- create watch
- list active watches for user
- deactivate watch
- add source to watch
- list sources for watch
- deactivate source
- insert listing if new
- list unnotified listings for watch
- mark listings as notified

Dedupe listings primarily by URL.

Add tests for:

- user creation
- watch creation
- source creation
- listing dedupe
- unnotified listing retrieval
- mark notified behaviour

---

## Phase 2 — Scoring + Conversions

Implement:

- USD to AUD conversion using env-configured static rate
- miles to kilometres conversion
- listing scoring using:
  - car query
  - keywords
  - excluded keywords

Scoring requirements:

- positive keywords increase score
- excluded keywords strongly penalise or reject
- return score and match reasons
- handle missing price or mileage safely

Add tests for:

- C5 Corvette manual HUD targa positive match
- automatic convertible negative/rejected match
- USD to AUD conversion
- miles to km conversion
- missing values

---

## Phase 3 — Mock Scraper Pipeline

Implement:

- `ScraperAdapter` interface
- `MockScraper`
- `ScrapeService`

The mock scraper should return hardcoded car listings including:

- strong C5 Corvette match
- automatic/convertible non-match
- listing with missing mileage
- listing with missing price

ScrapeService should:

1. Load active watches and active sources
2. Run scraper for each source
3. Score listings
4. Convert price/mileage
5. Insert new listings only
6. Not send Discord notifications immediately

Add tests for:

- mock scraper returns listings
- scrape service stores matching listings
- repeated scrape does not duplicate listings
- excluded keyword listing is rejected or heavily penalised

---

## Phase 4 — Source Test Behaviour

Implement source test behaviour using the mock scraper only.

A source test result should report:

- whether the URL was accepted
- number of listings found
- whether title parsing worked
- whether link parsing worked
- whether price parsing worked
- whether mileage parsing worked
- warnings for missing optional fields
- errors for critical failures

Add tests for:

- successful source test
- partial parse warning
- failed source test

---

## Phase 5 — Digest Generation

Implement digest formatting without Discord sending first.

Digest should include:

- watch name/query
- number of new listings
- title
- source
- original price
- converted price
- original mileage
- converted mileage
- score reasons
- link

Add tests for:

- digest with multiple listings
- no empty digest
- listings marked notified only after successful notification call, if notification layer exists

---

## Phase 6 — Discord Bot Layer, Only If Prior Phases Are Done

Implement basic Discord slash commands:

- `/ping`
- `/watch_add`
- `/watch_list`
- `/watch_remove`

If time permits, add:

- `/watch_source_add`
- `/watch_source_list`
- `/watch_source_test`

Rules:

- Commands must call service layer only.
- Commands must not access repositories directly.
- User-specific responses should be ephemeral.
- Use optional `DISCORD_GUILD_ID` for fast local slash command sync.

Do not overbuild Discord command handling if core services are incomplete.

---

# Testing Requirements

Run tests after each major phase.

Use:

```bash
pytest


If formatting/linting tools exist, run them too.

Do not leave the repo with failing tests.

If a test is too hard because the design is unclear, add a TODO in the test file and document the blocker in docs/11-overnight-progress.md.

Progress Log

Create or update:

docs/11-overnight-progress.md

Include:

completed work
files changed
tests added
tests passing/failing
known issues
next recommended prompt/task


Stop Conditions

Stop and write notes in docs/11-overnight-progress.md if:

architecture docs contradict each other
database design is unclear
tests cannot pass due to scaffold issues
Discord command implementation would require major redesign
dependency versions cause problems

Prefer a clean partial implementation with passing tests over a large broken implementation.

Final Expected State

By the end, aim for:

pytest passes
database layer works
mock scraper pipeline works
scoring/conversions work
digest formatting works
docs/11-overnight-progress.md exists

Real scraping can wait until the next session.