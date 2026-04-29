# Overnight Progress

## Completed Work

- Implemented SQLAlchemy database models for users, watches, sources, watch-source links, listings, watch listings, scrape attempts, and source test attempts.
- Implemented repository operations for:
  - creating/getting users by Discord id
  - creating/listing/deactivating watches
  - creating/deactivating sources
  - adding sources to watches
  - listing sources for watches
  - inserting listings with URL dedupe
  - listing unnotified watch listings
  - marking watch listings notified
  - recording scrape attempts
  - recording source test attempts
- Expanded core models for listing candidates, scoring results, source test results, and digest payloads.
- Implemented static USD to AUD conversion and miles to kilometres conversion.
- Implemented deterministic listing scoring with positive keyword reasons and excluded-keyword rejection.
- Implemented mock-only scraper adapter with hardcoded C5 Corvette listings.
- Implemented `ScrapeService` to run mock scraping, score, convert, persist, dedupe, and record scrape attempts without sending notifications.
- Implemented mock-only source test behaviour with structured warnings/errors and persisted test attempts.
- Implemented digest formatting from persisted pending listings.
- Added `requirements.txt` for reliable local dependency installation.

## Files Changed

- `.env.example`
- `.gitignore`
- `README.md`
- `requirements.txt`
- `src/car_watch_bot/config.py`
- `src/car_watch_bot/core/models.py`
- `src/car_watch_bot/core/conversions.py`
- `src/car_watch_bot/core/scoring.py`
- `src/car_watch_bot/db/database.py`
- `src/car_watch_bot/db/models.py`
- `src/car_watch_bot/db/repositories.py`
- `src/car_watch_bot/scrapers/base.py`
- `src/car_watch_bot/scrapers/mock.py`
- `src/car_watch_bot/services/scrape_service.py`
- `src/car_watch_bot/services/source_service.py`
- `src/car_watch_bot/services/digest_service.py`
- `tests/conftest.py`
- `tests/test_conversions.py`
- `tests/test_digest_service.py`
- `tests/test_repositories.py`
- `tests/test_scoring.py`
- `tests/test_scrape_service.py`
- `tests/test_source_service.py`

## Tests Added

- Repository tests for user creation, watch creation, source assignment, listing dedupe, unnotified listing retrieval, and mark-notified behaviour.
- Conversion tests for USD to AUD, miles to kilometres, and missing values.
- Scoring tests for a strong C5 Corvette manual HUD targa match, automatic convertible rejection, and missing price/mileage.
- Mock scraper and scrape service tests for deterministic listings, matched-only persistence, repeated scrape dedupe, and excluded listing rejection.
- Source test tests for success, partial parse warning, and failure.
- Digest tests for multiple listings, no empty digest, and marking listings notified after a successful digest call.

## Test Results

- `pytest`: 24 passed.
- `python3 -m compileall src tests`: passed.

## Known Issues

- The local shell is using Python 3.10.12, while project metadata requires Python 3.11+.
- `pip install -e ".[dev]"` did not work with the local packaging toolchain, so `requirements.txt` was added and README setup now uses `pip install -r requirements.txt`.
- Discord slash commands were not implemented in this pass because the core prototype work took priority and the instructions said not to overbuild command handling if core services were incomplete.
- Real website scraping remains intentionally unimplemented.

## Next Recommended Prompt

Implement the next MVP slice: add service-layer watch/source management methods, then implement thin Discord slash commands for `/ping`, `/watch_add`, `/watch_list`, and `/watch_remove` that call services only. Keep tests passing and avoid repository access from command handlers.
