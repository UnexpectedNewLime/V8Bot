# RALPH Loop

Use this loop while stabilizing scraper work.

## Meaning

RALPH means:

1. **Run** the current scraper or service flow.
2. **Analyze** the returned listings, warnings, database rows, and tests.
3. **Learn** what the source actually exposes.
4. **Patch** the smallest correct change.
5. **Harden** with tests and another live/manual check.

## Source Of Truth

For AutoTempest implementation details, use:

```text
docs/12-autotempest-source-of-truth.md
```

Do not rely on chat memory when this file has the relevant rule.

## Required Commands

After scraper changes, run:

```bash
pytest
python3 -m compileall src tests scripts
python3 scripts/manual_autotempest_scrape.py
PYTHONPATH=src python scripts/local_watch_flow_check.py --watch-id 1
```

## Pass Criteria

The loop is not complete until:

- Tests pass.
- Manual scrape returns exact vehicle listing URLs.
- Local service flow stores new listings with exact vehicle URLs.
- No new AutoTempest `/results` listing is created.
- Facebook Marketplace is not scraped.

## Database Cleanup

Old bad rows may remain from earlier scraper versions. They are not evidence of a current scraper failure.

To remove old AutoTempest search-url listings from a local test database:

```sql
delete from watch_listings
where listing_id in (
  select id from listings
  where url like 'https://www.autotempest.com/results%'
);

delete from listings
where url like 'https://www.autotempest.com/results%';
```

Only run cleanup on a local/test database.

