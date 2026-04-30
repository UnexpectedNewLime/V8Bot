# V8Bot

Purpose-built Discord bot for scheduled car listing watch digests.

V8Bot lets Discord users create car watches with keywords, excluded keywords,
preferred currency, distance unit, listing sources, and a notification time.
The bot scrapes sources, dedupes listings, stores matches, and posts digest
messages to Discord.

Current source status:

- AutoTempest is the first real source adapter.
- Other sources remain mock-first until deliberately implemented.
- Facebook Marketplace is not supported in the MVP.

## Getting Started For Development

Use Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` before starting the bot:

```text
DISCORD_BOT_TOKEN=<your bot token>
DISCORD_GUILD_ID=<your test server id>
DATABASE_URL=sqlite:///./car_watch_bot.sqlite3
DEFAULT_TIMEZONE=Australia/Sydney
DEFAULT_CURRENCY=AUD
DEFAULT_DISTANCE_UNIT=km
USD_TO_AUD_RATE=1.50
SCRAPE_INTERVAL_MINUTES=60
DIGEST_POLL_INTERVAL_MINUTES=1
SCRAPER_USER_AGENT=V8Bot/0.1 (+local manual testing)
SCRAPER_TIMEOUT_SECONDS=10
SCRAPER_MIN_INTERVAL_SECONDS=2
LOG_LEVEL=INFO
```

`DISCORD_GUILD_ID` is optional, but strongly recommended for development
because guild slash commands sync much faster than global slash commands.

Never commit `.env`. It contains secrets and local runtime settings.

## Create A Discord Bot Token

In the Discord Developer Portal:

1. Create **New Application**.
2. Open **Bot**.
3. Select **Create Bot** if a bot does not exist yet.
4. Copy the **Bot Token**.
5. Paste it into `.env` as `DISCORD_BOT_TOKEN`.

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
3. Paste it into `.env` as `DISCORD_GUILD_ID`.

## Run The Bot Locally

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
- `/watch_remove`
- `/watch_keyword_add`
- `/watch_keyword_remove`
- `/watch_exclude_add`
- `/watch_exclude_remove`
- `/watch_source_add`
- `/watch_source_list`
- `/watch_source_remove`
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
source_name: AutoTempest
scrape_now: True
```

Expected result:

- The command response is private to the user.
- Listing messages are posted publicly to the channel.
- Each listing is its own embed.
- Prices use whole-number car formatting, such as `AUD 26,850`.

You can also run the flow manually:

```text
/watch_add
/watch_source_add
/watch_scrape_now
/watch_listings
```

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
`notify_time` matches the current minute.

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
select id, title, url, price_amount, mileage_value from listings;
```

## Podman Deployment

Podman is the default container engine for local or Proxmox-style deployment.
The setup uses Python 3.11, installs `requirements.txt`, loads configuration
from `.env`, and stores SQLite data in `./data` on the host.

The default compose file is rootless-Podman friendly. It uses the `:U` volume
flag so the non-root container user can write the SQLite database under
`./data`.

On SELinux-enabled hosts, create an untracked local override so Podman also
relabels the bind mount:

```yaml
services:
  car-watch-bot:
    volumes:
      - ./data:/data:Z,U
```

Prepare:

```bash
mkdir -p data
cp .env.example .env
```

Set at least:

```text
DISCORD_BOT_TOKEN=<prod bot token>
DISCORD_GUILD_ID=<prod or test server id>
```

In Compose, `DATABASE_URL` is overridden to:

```text
sqlite:////data/car_watch_bot.sqlite3
```

This maps to `./data/car_watch_bot.sqlite3` on the host.

Build:

```bash
podman-compose build
```

Start:

```bash
podman-compose up -d
```

View status:

```bash
podman ps
```

View logs:

```bash
podman-compose logs -f car-watch-bot
```

Stop:

```bash
podman-compose down
```

Update after `git pull`:

```bash
git pull
podman-compose build
podman-compose up -d
podman-compose logs -f car-watch-bot
```

Verify persistence:

```bash
sqlite3 data/car_watch_bot.sqlite3 ".tables"
```

Persistent data:

- SQLite database: `./data/car_watch_bot.sqlite3`
- Application logs: stdout/stderr via `podman-compose logs`

No ports are exposed. Discord bots connect outbound to Discord.

On older Podman versions, you may see a CNI firewall config warning. If the
container starts, connects to Discord, and writes the SQLite database, that
warning is not blocking runtime.

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
- Add more sources (currently only Autotempest), Biggest win would be carsales scraping here
- Move all messages to post in a thread to avoid spam
- Have different watches on different threads
