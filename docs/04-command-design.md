# Command Design

## Principles

- Use Discord slash commands through `discord.py`.
- Defer responses for operations that may touch storage, scheduling, or source testing.
- Keep command handlers thin and delegate business logic to core services.
- Return clear ephemeral responses for configuration commands.
- Send listing results only through scheduled digests, not command responses.
- Scope user-facing watch and source selectors to the interacting Discord user.

## Watch Commands

### `/watch add`

Creates a new watch.

Options:

- `name`: required string.
- `keywords`: required string, comma-separated.
- `exclude`: optional string, comma-separated.
- `currency`: optional string, default from config.
- `distance_unit`: optional choice, `km` or `mi`, default `km`.
- `notification_time`: required string in `HH:MM` 24-hour format.
- `timezone`: optional IANA timezone.
- `sources`: optional string or choices, depending on command registration strategy.

Behaviour:

- Validate keywords and notification time.
- Create or load the Discord user.
- Create the watch.
- Attach selected sources or the default mock source if no source is selected.
- Respond ephemerally with the watch summary.
- Do not scrape immediately unless a future explicit preview command is added.

### `/watch list`

Lists the user's watches.

Options:

- `active_only`: optional boolean, default true.

Behaviour:

- Show watch names, notification times, enabled sources, and active status.

### `/watch show`

Shows one watch.

Options:

- `watch`: required watch selector.

Behaviour:

- Show keywords, exclusions, currency, distance unit, notification time, channel, and sources.

### `/watch edit`

Modifies an existing watch.

Options:

- `watch`: required watch selector.
- `name`: optional string.
- `keywords`: optional comma-separated string.
- `exclude`: optional comma-separated string.
- `currency`: optional string.
- `distance_unit`: optional choice.
- `notification_time`: optional `HH:MM`.
- `timezone`: optional IANA timezone.
- `active`: optional boolean.

Behaviour:

- Apply only provided fields.
- Validate the resulting watch.
- Increment the watch criteria version when keywords, exclusions, or other matching criteria change.
- Respond with the updated summary.

### `/watch remove`

Removes or deactivates a watch.

Options:

- `watch`: required watch selector.
- `confirm`: required boolean.

Behaviour:

- If confirmed, deactivate the watch for MVP.
- Keep historical listings and digest records.

### `/watch sources add`

Enables a source for a watch.

Options:

- `watch`: required watch selector.
- `source`: required source selector.

Behaviour:

- Add or re-enable the watch-source association.
- Increment the watch criteria version.

### `/watch sources remove`

Disables a source for a watch.

Options:

- `watch`: required watch selector.
- `source`: required source selector.

Behaviour:

- Disable association.
- Do not delete the source globally.
- Increment the watch criteria version.

## Source Commands

### `/source add`

Adds a user-owned custom website source.

Options:

- `name`: required string.
- `url`: required string.

Behaviour:

- Reject Facebook Marketplace URLs in v1.
- Store the source as `custom_website`.
- Run the source test by default or instruct user to run `/source test`.
- Do not enable production scraping for the custom website in MVP.
- Make clear that attaching the source to a watch will not produce scheduled listings until a real adapter exists.

### `/source test`

Tests whether a custom website source appears usable.

Options:

- `url`: required string, or `source`: existing source selector.

Behaviour:

- Reject Facebook Marketplace URLs in v1.
- Fetch the page with `httpx` only when network-based testing is enabled.
- Parse HTML with BeautifulSoup.
- Check for basic page accessibility and listing-like anchors.
- Return an ephemeral result with status and notes.
- Do not store listings.
- Do not enable real scraping.
- Record the test attempt for diagnostics and update the source's latest test status when testing an existing source.

### `/source list`

Lists available sources.

Options:

- `mine_only`: optional boolean.

Behaviour:

- Show built-in sources and user-owned custom website sources.
- Indicate which sources are mock-only or test-only in MVP.

### `/source remove`

Removes or deactivates a user-owned source.

Options:

- `source`: required source selector.
- `confirm`: required boolean.

Behaviour:

- Deactivate only sources owned by the user.
- Built-in sources cannot be removed.
- Existing historical listings remain.

## Admin Commands

Optional MVP admin commands:

- `/admin scheduler status`.
- `/admin scrape run_mock`.
- `/admin scrape attempts`.
- `/admin digest run_due`.

These should be restricted by configured admin Discord user ids or guild permissions.

## Digest Message Shape

Each listing item should include:

- Title.
- Converted price in preferred currency when available.
- Mileage in the watch's distance unit, default kilometres.
- Location when available.
- Source name.
- Link.

Digest header should include:

- Watch name.
- Number of new listings.
- Collection window.

If Discord embed limits are reached, split the digest into multiple messages.
