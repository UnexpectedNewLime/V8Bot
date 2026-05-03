# V8Bot

Purpose-built Discord bot for scheduled car listing watch digests.

V8Bot lets Discord users create car watches with keywords, excluded keywords,
preferred currency, distance unit, listing sources, and a notification time.
The bot scrapes sources, dedupes listings, stores matches, and posts digest
messages to Discord.

Current source status:

- AutoTempest supports static/queue result scraping.
- Cars On Line, Corvette Magazine classifieds, and VetteFinders support static
  HTML scraping.
- Cars.com, Gateway Classic Cars, and Streetside Classics are not registered
  because simple polite HTTP requests currently receive challenge responses.
- Carsales still needs a concrete target URL before implementation.
- Facebook Marketplace is not supported in the MVP.

## Create A Discord Bot Token

In the Discord Developer Portal:

1. Create **New Application**.
2. Open **Bot**.
3. Select **Create Bot** if a bot does not exist yet.
4. Copy the **Bot Token**.
5. Keep it ready for `DISCORD_BOT_TOKEN` in `.env`.

Then invite the bot to your test server:

1. Open **OAuth2**.
2. Open **URL Generator**.
3. Select scopes:
   - `bot`
   - `applications.commands`
4. Select bot permissions:
   - `Send Messages`
   - `Embed Links`
   - `Use Slash Commands`
5. Open the generated URL.
6. Invite the bot to your server.

## Get The Guild ID

Enable Developer Mode in Discord:

1. Go to **User Settings**.
2. Open **Advanced**.
3. Turn on **Developer Mode**.

Copy the server ID:

1. Right-click your server icon in the left sidebar.
2. Click **Copy Server ID**.
3. Keep it ready for `DISCORD_GUILD_ID` in `.env`.

## Development Setup

Podman is the default way to run V8Bot locally or on a small host. The compose
setup uses Python 3.11, installs `requirements.txt`, loads configuration from
`.env`, and stores SQLite data in `./data` on the host. It requires Podman and
`podman-compose`.

Run the setup script from the repository root:

```bash
scripts/setup_dev.sh
```

The script creates `data/`, copies `.env.example` to `.env` when `.env` does
not already exist, prompts for the Discord bot token and guild ID when they are
missing, checks for Podman tooling, and prints the next run commands.

If the script fails with a permission error, make it executable and run it
again:

```bash
chmod +x scripts/setup_dev.sh
scripts/setup_dev.sh
```

If the script cannot be used, run the manual prep:

```bash
mkdir -p data
cp .env.example .env
```

Only run the copy command when `.env` does not already exist.

If you skipped the prompts, edit `.env` before starting the bot. Set at least:

```text
DISCORD_BOT_TOKEN=<your bot token>
DISCORD_GUILD_ID=<your test server id>
```

The copied `.env.example` includes the rest of the supported local settings.

In Compose, `DATABASE_URL` is overridden to:

```text
sqlite:////data/car_watch_bot.sqlite3
```

This maps to `./data/car_watch_bot.sqlite3` on the host.

Build and start:

```bash
podman-compose build
podman-compose up -d
```

View status and logs:

```bash
podman ps
podman-compose logs -f car-watch-bot
```

Stop the bot:

```bash
podman-compose down
```

For the Prod Server to update after `git pull`:

```bash
git pull
podman-compose build
podman-compose up -d
podman-compose logs -f car-watch-bot
```

The default compose file is rootless-Podman friendly. It uses the `:U` volume
flag so the non-root container user can write the SQLite database under
`./data`.

Persistent data:

- SQLite database: `./data/car_watch_bot.sqlite3`
- Application logs: stdout/stderr via `podman-compose logs`

No ports are exposed. Discord bots connect outbound to Discord.

On older Podman versions, you may see a CNI firewall config warning. If the
container starts, connects to Discord, and writes the SQLite database, that
warning is not blocking runtime.

On SELinux-enabled hosts, create an untracked local override so Podman also
relabels the bind mount:

```yaml
services:
  car-watch-bot:
    volumes:
      - ./data:/data:Z,U
```

`DISCORD_GUILD_ID` is optional, but strongly recommended for development
because guild slash commands sync much faster than global slash commands.

Never commit `.env`. It contains secrets and local runtime settings.

## Run The Bot Without Containers

Use Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Start the bot:

```bash
PYTHONPATH=src python -m car_watch_bot.main
```

Expected startup logs:

```text
logging in using static token
synced guild commands
Scheduler started
Shard ID None has connected to Gateway
```

The current Discord interface registers:

- `/ping`
- `/watch_add`
- `/watch_list`
- `/watch_show`
- `/watch_edit`
- `/watch_remove`
- `/watch_keyword_add`
- `/watch_keyword_remove`
- `/watch_exclude_add`
- `/watch_exclude_remove`
- `/watch_source_add`
- `/watch_source_list`
- `/watch_source_remove`
- `/watch_source_remove_menu`
- `/watch_source_test`
- `/watch_scrape_now`
- `/watch_listings`
- `/watch_notify_time`
- `/watch_currency`
- `/watch_distance_unit`

## Recommended Discord Test Flow

Use the one-command setup path:

```text
/watch_add
car_query: C5 Corvette
keywords: manual, targa, hud
exclude_keywords: automatic, convertible
notify_time: 22:08
source_url: https://www.autotempest.com/results?localization=any&make=chevrolet&maxyear=2001&minyear=2001&model=corvette&transmission=man&zip=90210
scrape_now: True
```

`source_name` is optional. If omitted, the bot derives a name from the domain.
`source_url` may contain multiple URLs separated by spaces, commas, or new
lines. Pasted Markdown links are also accepted. Generated names are made unique
per user, such as `cars-on-line` and `cars-on-line 2`.

Expected result:

- The command response is private to the user.
- Listing messages are posted publicly to the watch thread.
- Each listing is its own embed.
- Each listing embed has Star and Delete buttons.
- Prices use whole-number car formatting, such as `AUD 26,850`.
- Embeds include optional location, first seen, last seen, seller/dealer details,
  listing images, and price-change details when the stored listing data has
  those values.

Listing action buttons update the stored watch-listing status for the user who
owns the watch. Star copies the listing into a thread named from the normal
watch thread with `Starred ` prefixed, with only an Unstar button, and keeps it
visible in `/watch_listings`.
Delete opens a confirmation modal, removes the clicked Discord message, and
keeps the listing out of later scrape output for that watch. The delete modal
includes an optional free-text reason field for future analytics. Unstar opens
a confirmation modal, removes the starred-thread copy, and leaves the original
watch-thread listing active.

You can also run the flow manually:

```text
/watch_add
/watch_show
/watch_edit
/watch_source_add
/watch_scrape_now
/watch_listings
```

Commands that accept a `watch_id` offer Discord autocomplete scoped to your
active watches. `/watch_source_remove` also autocompletes `source_id` after a
watch is selected, and `/watch_source_remove_menu` lets you remove a source from
an ephemeral select menu.

`/watch_source_add` accepts one or more URLs in its `url` field. The optional
`name` field can only be used with a single URL.

Use `/watch_show watch_id:<id>` for the full watch configuration, including
delivery ids and source details. Use `/watch_edit watch_id:<id>` with only the
fields you want to change. Supported edit fields include `car_query`,
`watch_name`, `keywords`, `exclude_keywords`, `clear_exclusions`, `notify_time`,
`timezone`, `currency`, `distance_unit`, `channel_id`, `thread_id`,
`clear_channel`, `clear_thread`, `use_current_channel`, and `active`.

## Local Scrape Flow Without Discord

Use `scripts/local_scrape_flow.py` to exercise the same service-layer flow
without starting the bot:

```bash
PYTHONPATH=src python scripts/local_scrape_flow.py \
  --car-query "C5 Corvette" \
  --keywords "manual, targa, hud" \
  --exclude-keywords "automatic, convertible" \
  --notify-time "22:08" \
  --source-name "AutoTempest Local" \
  --source-url "https://www.autotempest.com/results?localization=any&make=chevrolet&maxyear=2001&minyear=2001&model=corvette&transmission=man&zip=90210"
```

This command will:

- create a local watch unless `--watch-id` is supplied
- add or reuse the named source
- run the source test
- scrape the source unless `--no-scrape` is supplied
- print stored pending listings as JSON

To reuse an existing watch:
-Move all messages to post in a thread to avoid spam -Have different watches on different threads


```bash
PYTHONPATH=src python scripts/local_scrape_flow.py \
  --watch-id 1 \
  --source-name "AutoTempest Local" \
  --source-url "https://www.autotempest.com/results?localization=any&make=chevrolet&maxyear=2001&minyear=2001&model=corvette&transmission=man&zip=90210"
```

## Manual AutoTempest Scrape

For adapter-level debugging:

```bash
python scripts/manual_autotempest_scrape.py
```

You can pass a specific AutoTempest URL as the first argument. This command
uses `SCRAPER_USER_AGENT`, `SCRAPER_TIMEOUT_SECONDS`, and
`SCRAPER_MIN_INTERVAL_SECONDS` from config.

By default, the command returns exact vehicle listing URLs only.

## Scheduled Jobs

When the bot is running, APScheduler starts:

- scraping every `SCRAPE_INTERVAL_MINUTES`
- digest checks every minute

Digest checks send only stored, unnotified listings for watches whose local
`notify_time` matches the current minute. Digest listing embeds include the same
listing action buttons as manual scrape output. Successfully sent digest rows
are marked `sent`, while starred and inactive rows are not treated as pending
digest items.

## Listing Embeds

Listing embeds always include the listing title/link, source, converted price,
original price, converted mileage, original mileage, and score reasons. When
available, embeds also include:

- location from the normalized listing row
- first seen and last seen timestamps from stored listing rows, shown in Sydney
  local time
- seller or dealer details extracted from scraper `raw_payload`
- a thumbnail image URL extracted from scraper `raw_payload`
- price-change text when V8Bot has stored a prior price snapshot

V8Bot stores price baselines in listing `raw_payload` for rows created or
refreshed by this version. Older rows without that metadata will not claim a
price change until a future scrape stores enough comparison data.

## Run Tests

```bash
pytest
python -m compileall src tests scripts
```

Tests do not connect to Discord and do not make live network calls.

## Inspect Local SQLite Data

Local development default:

```bash
sqlite3 car_watch_bot.sqlite3 ".tables"
```

Container default:

```bash
sqlite3 data/car_watch_bot.sqlite3 ".tables"
```

Useful queries:

```sql
select id, discord_user_id from users;
select id, user_id, name, query, notification_time from watches;
select id, name, kind, base_url, is_active from sources;
select id, title, url, price_amount, mileage_value, location_text, first_seen_at, last_seen_at
from listings;
select watch_id, listing_id, status, sent_at from watch_listings;
```

## Docker Deployment

Docker is supported as a secondary runtime. Use the Docker override file because
Docker does not support Podman's `:U` volume option.

Check tooling:

```bash
docker --version
docker compose version
```

Build:

```bash
docker compose -f docker-compose.yml -f docker-compose.docker.yml build
```

Start:

```bash
docker compose -f docker-compose.yml -f docker-compose.docker.yml up -d
```

View logs:

```bash
docker compose -f docker-compose.yml -f docker-compose.docker.yml logs -f car-watch-bot
```

Stop:

```bash
docker compose -f docker-compose.yml -f docker-compose.docker.yml down
```

Update after `git pull`:

```bash
git pull
docker compose -f docker-compose.yml -f docker-compose.docker.yml build
docker compose -f docker-compose.yml -f docker-compose.docker.yml up -d
docker compose -f docker-compose.yml -f docker-compose.docker.yml logs -f car-watch-bot
```

Verify persistence:

```bash
sqlite3 data/car_watch_bot.sqlite3 ".tables"
```

## Production Notes

- Use a dedicated production Discord application and bot token.
- Use a dedicated `.env` on the host.
- Back up `./data/car_watch_bot.sqlite3`.
- Do not run the same bot token in multiple places at once.
- Keep `.env` and `./data` out of git.
- Confirm the host has outbound HTTPS/DNS access.

## Documentation

Start with:

- `docs/00-agent-rules.md`
- `docs/00-read-this-first.md`
- `docs/08-style-guide.md`
- `docs/09-engineering-principles.md`

## TODO
- Add carsales scraping after a concrete target URL and permission posture are
  decided.
