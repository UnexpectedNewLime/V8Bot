# AutoTempest Source Of Truth

This file is the current source of truth for AutoTempest scraper work.

## Goal

AutoTempest scraping must store exact vehicle listing URLs, not search URLs, not page fragments, and not comparison/search landing pages.

Invalid examples:

- `https://www.autotempest.com/results?...`
- `https://www.autotempest.com/results?...#te-results`
- `/external-source/...` comparison/search links
- Facebook Marketplace links

Valid examples are vehicle detail URLs returned by AutoTempest's result JSON:

- Hemmings listing detail URLs
- Cars.com vehicle detail URLs
- eBay item URLs
- TrueCar listing URLs

## Current Discovery

The static AutoTempest HTML does not render concrete vehicle cards. It contains templates plus JavaScript metadata.

The browser fetches real listing data from:

```text
https://www.autotempest.com/queue-results
```

The response contains JSON with `results[]` objects. These objects include usable fields:

- `title`
- `url`
- `price`
- `mileage`
- `location`
- `sourceName`
- `sitecode`
- `backendSitecode`
- `externalId`
- `vin`
- `id`

## Queue Sources

Use only queue-backed internal sources for MVP:

- `te`
- `hem`
- `cs`
- `cv`
- `cm`
- `eb`
- `ot`

Do not use Facebook Marketplace:

- `fbm` is excluded.

SearchTempest/craigslist:

- `st` uses a different direct endpoint shape and should remain out until implemented deliberately.

## Queue Token

AutoTempest JavaScript computes a queue token:

```text
sha256(decodeURIComponent(jQuery.param(params)) + QUEUE_TOKEN_SECRET)
```

The discovered token secret is currently:

```text
d8007486d73c168684860aae427ea1f9d74e502b06d94609691f5f4f2704a07f
```

This is public client-side JavaScript data, not a private repo secret. If AutoTempest changes their frontend bundle, this scraper may need updating.

## Scraper Behaviour

Preferred flow:

1. Fetch the AutoTempest results page.
2. Extract `searchParams` from page JavaScript.
3. Extract available `.source-results` source codes.
4. For each supported queue source, call `queue-results`.
5. Convert JSON result objects to `ListingCandidate`.
6. Return only candidates with absolute HTTP(S) vehicle URLs.

Fallback flow:

- Existing saved HTML fixture parsing remains for tests and static compatibility.
- Comparison links may be exposed only for diagnostics, never stored by default.

## Warnings

The scraper should warn when:

- Facebook Marketplace is skipped.
- Queue sources return no exact listings.
- Queue fetch fails and HTML fallback is used.

## Local Verification

Run the manual scraper:

```bash
python scripts/manual_autotempest_scrape.py
```

Run the local service flow:

```bash
PYTHONPATH=src python scripts/local_watch_flow_check.py --watch-id 1
```

Expected successful behaviour:

- `listing_count` should be greater than zero for the known Corvette test URL when queue JSON is available.
- Listing URLs should point to exact vehicle detail pages.
- No AutoTempest `/results` URL should be stored.

