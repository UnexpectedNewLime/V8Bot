# Command Design

## Principles

- Commands are Discord slash commands registered with `discord.py`.
- Command names are flat underscore names.
- Configuration command responses are ephemeral.
- Commands defer before doing service work.
- Listing output is sent as public embeds in the watch's Discord thread.
- Commands call services rather than repositories.
- Watch and source actions are scoped to the interacting Discord user.

## Registered Commands

The current command tree contains:

- `/ping`.
- `/watch_add`.
- `/watch_list`.
- `/watch_remove`.
- `/watch_keyword_add`.
- `/watch_keyword_remove`.
- `/watch_exclude_add`.
- `/watch_exclude_remove`.
- `/watch_source_add`.
- `/watch_source_list`.
- `/watch_source_remove`.
- `/watch_source_test`.
- `/watch_scrape_now`.
- `/watch_listings`.
- `/watch_notify_time`.
- `/watch_currency`.
- `/watch_distance_unit`.

## `/watch_add`

Options:

- `car_query`: required string.
- `keywords`: required comma-separated string.
- `notify_time`: required `HH:MM`.
- `exclude_keywords`: optional comma-separated string.
- `source_url`: optional field containing one or more URLs.
- `source_name`: optional name, only allowed with a single URL.
- `scrape_now`: optional boolean, default true.

Behavior:

- Creates a watch for the interacting user.
- Stores the current guild and channel as the delivery target.
- Parses multiple source URLs from spaces, commas, new lines, or Markdown links.
- Adds and tests each supplied source URL.
- Rejects the whole source name usage if `source_name` is supplied with multiple
  URLs.
- If `scrape_now` is true and at least one source was added, scrapes the watch,
  posts only newly pending listings to the watch thread, and marks those posted
  listings sent.
- Returns an ephemeral setup summary.

## `/watch_list`

Lists the user's active watches with:

- Watch id.
- Car query.
- Included keywords.
- Excluded keywords.
- Notification time.
- Preferred currency and distance unit.
- Active source count.

## `/watch_remove`

Options:

- `watch_id`: required integer.

Behavior:

- Deactivates the owned active watch.
- Keeps historical listings and source rows.

## Keyword Commands

`/watch_keyword_add` and `/watch_keyword_remove` modify included keywords.
`/watch_exclude_add` and `/watch_exclude_remove` modify excluded keywords.

Options:

- `watch_id`: required integer.
- `keyword`: required string.

Behavior:

- Rejects blank keywords and keywords containing commas.
- Prevents removing the last included keyword.
- Increments criteria version when the stored keyword list changes.
- Returns an ephemeral watch summary.

## Source Commands

### `/watch_source_add`

Options:

- `watch_id`: required integer.
- `url`: required field containing one or more URLs.
- `name`: optional name, only allowed with one URL.

Behavior:

- Parses URLs using the same helper as `/watch_add`.
- Infers source kind by domain.
- Runs source tests before storing/attaching accepted sources.
- Adds accepted sources to the watch.
- Reports per-URL add failures without exposing full raw URLs in compact
  summaries.
- Runtime app configuration rejects unregistered source kinds.

### `/watch_source_list`

Options:

- `watch_id`: required integer.

Behavior:

- Lists active enabled sources attached to the watch.
- Shows source id, name, kind, and domain.

### `/watch_source_remove`

Options:

- `watch_id`: required integer.
- `source_id`: required integer.

Behavior:

- Disables the watch-source association.
- Does not delete source or listing history.

### `/watch_source_test`

Options:

- `url`: required URL.

Behavior:

- Tests the URL and records a source test attempt.
- Known source kinds use their registered adapter.
- Unsupported domains use the diagnostic scraper and return "Diagnostic only"
  unless a custom test adapter is injected.
- Facebook URLs are rejected.
- Source tests never create listing rows.

## Listing Commands

### `/watch_scrape_now`

Options:

- `watch_id`: required integer.

Behavior:

- Scrapes each active enabled source attached to the owned watch when a matching
  adapter exists.
- Skips sources with no adapter and reports warnings.
- Posts newly pending listings as embeds with listing action buttons in the
  watch thread.
- Marks the posted listing ids sent.
- Returns an ephemeral scrape summary.

### `/watch_listings`

Options:

- `watch_id`: required integer.

Behavior:

- Builds listing history for visible watch listings, including `pending_digest`,
  `sent`, and `starred` rows.
- Posts embeds with listing action buttons in the watch thread.
- Does not mark listings sent.
- The command description currently says "pending watch listings", but the
  implementation includes sent listing history too.

### Listing Action Buttons

Listing embeds expose Star and Delete buttons. Button clicks update
`watch_listings.status` through the listing service and are scoped to the
Discord user who owns the watch.

Star marks the watch-listing `starred` and copies the listing embed to a
per-watch shortlist thread named `Starred <car search name>`. Delete first asks
for confirmation, then marks the watch-listing `inactive`, deletes the clicked
Discord message, and prevents the row from becoming pending again on later
scrapes.

## Preference Commands

`/watch_notify_time`, `/watch_currency`, and `/watch_distance_unit` update watch
preferences.

Options:

- `watch_id`: required integer.
- `notify_time`, `currency`, or `distance_unit` depending on command.

Behavior:

- Notification time must be `HH:MM`.
- Currency must be a three-letter alphabetic code.
- Distance unit must be `km` or `mi`.
- Returns an ephemeral watch summary.

## Digest Message Shape

Each listing is rendered as its own Discord embed. The embed contains:

- Listing title linked to the listing URL.
- Optional heading and query in the description.
- Source.
- Converted price.
- Original price.
- Converted mileage.
- Original mileage.
- Score reasons.

Scheduled no-update digests send a short text message to the watch thread.

## Discord Limits

Ephemeral text responses are split into Discord-safe chunks. Listing embeds are
sent one per listing rather than packed into a single message.
