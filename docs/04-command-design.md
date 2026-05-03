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
- `/watch_show`.
- `/watch_edit`.
- `/watch_remove`.
- `/watch_keyword_add`.
- `/watch_keyword_remove`.
- `/watch_exclude_add`.
- `/watch_exclude_remove`.
- `/watch_source_add`.
- `/watch_source_list`.
- `/watch_source_remove`.
- `/watch_source_remove_menu`.
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

## `/watch_show`

Options:

- `watch_id`: required integer with user-scoped autocomplete.

Behavior:

- Shows a detailed private view of an owned watch.
- Includes inactive owned watches so users can inspect watches deactivated by
  `/watch_remove` or `/watch_edit active:false`.
- Shows name, car query, active status, keywords, exclusions, notification time,
  timezone, currency, distance unit, delivery ids, criteria version, active
  source count, and source details.

## `/watch_edit`

Options:

- `watch_id`: required integer with user-scoped autocomplete.
- `car_query`: optional replacement search query.
- `watch_name`: optional replacement display/thread name.
- `keywords`: optional replacement comma-separated included keyword list.
- `exclude_keywords`: optional replacement comma-separated excluded keyword
  list.
- `clear_exclusions`: optional boolean to clear all excluded keywords.
- `notify_time`: optional replacement `HH:MM` notification time.
- `timezone`: optional replacement IANA timezone, such as `Australia/Sydney`.
- `currency`: optional replacement three-letter currency code.
- `distance_unit`: optional replacement `km` or `mi`.
- `channel_id`: optional replacement Discord channel id.
- `thread_id`: optional replacement Discord thread id.
- `clear_channel`: optional boolean that clears the stored channel and thread.
- `clear_thread`: optional boolean that clears only the stored thread.
- `use_current_channel`: optional boolean that stores the current command
  channel and guild as the delivery target.
- `active`: optional boolean. `false` deactivates the watch; `true` reactivates
  an inactive owned watch.

Behavior:

- Omitted fields are left unchanged.
- Validation happens in `WatchService`.
- Query, included keyword, and excluded keyword changes increment
  `criteria_version` once per edit.
- Setting a new channel clears the old thread unless a replacement thread id is
  supplied in the same edit.
- Returns an ephemeral updated watch detail view, or an unchanged view when no
  stored fields changed.

## `/watch_remove`

Options:

- `watch_id`: required integer with user-scoped autocomplete.

Behavior:

- Deactivates the owned active watch.
- Keeps historical listings and source rows.

## Keyword Commands

`/watch_keyword_add` and `/watch_keyword_remove` modify included keywords.
`/watch_exclude_add` and `/watch_exclude_remove` modify excluded keywords.

Options:

- `watch_id`: required integer with user-scoped autocomplete.
- `keyword`: required string.

Behavior:

- Rejects blank keywords and keywords containing commas.
- Prevents removing the last included keyword.
- Increments criteria version when the stored keyword list changes.
- Returns an ephemeral watch summary.

## Source Commands

### `/watch_source_add`

Options:

- `watch_id`: required integer with user-scoped autocomplete.
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

- `watch_id`: required integer with user-scoped autocomplete.

Behavior:

- Lists active enabled sources attached to the watch.
- Shows source id, name, kind, and domain.

### `/watch_source_remove`

Options:

- `watch_id`: required integer with user-scoped autocomplete.
- `source_id`: required integer with source autocomplete scoped to the selected
  owned watch.

Behavior:

- Disables the watch-source association.
- Does not delete source or listing history.

### `/watch_source_remove_menu`

Options:

- `watch_id`: required integer with user-scoped autocomplete.

Behavior:

- Lists active enabled sources attached to the watch in an ephemeral select
  menu.
- Removes the chosen source from the watch.
- Limits the select menu to Discord's first 25 active source options.
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

- `watch_id`: required integer with user-scoped autocomplete.

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

- `watch_id`: required integer with user-scoped autocomplete.

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
per-watch shortlist thread named from the normal watch thread with `Starred `
prefixed. The starred copy shows only an Unstar button. Delete opens a
confirmation modal, then marks the watch-listing `inactive`, deletes the
clicked Discord message, and prevents the row from becoming pending again on
later scrapes. The delete modal includes an optional free-text reason field;
the reason is available to the handler for logging and future analytics. Unstar
opens a confirmation modal, removes the starred-thread copy, and restores the
watch-listing to normal sent history without deactivating it.

## Preference Commands

`/watch_notify_time`, `/watch_currency`, and `/watch_distance_unit` update watch
preferences.

Options:

- `watch_id`: required integer with user-scoped autocomplete.
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
- Location, when known.
- First seen and last seen timestamps.
- Seller/dealer details from stored scraper metadata, when known.
- Thumbnail image from stored scraper metadata, when known.
- Price-change details only when stored historical price metadata supports a
  reliable comparison.
- Score reasons.

Scheduled no-update digests send a short text message to the watch thread.

## Discord Limits

Ephemeral text responses are split into Discord-safe chunks. Listing embeds are
sent one per listing rather than packed into a single message.
