#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

missing_tools=()

for tool in podman podman-compose; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    missing_tools+=("$tool")
  fi
done

mkdir -p data
echo "Created data/ for the container SQLite database."

if [[ -f .env ]]; then
  echo "Found existing .env; leaving it unchanged."
else
  cp .env.example .env
  echo "Created .env from .env.example."
fi

if ((${#missing_tools[@]} > 0)); then
  echo
  echo "Missing required Podman tooling: ${missing_tools[*]}"
  echo "Install the missing tool(s), then rerun this script or continue with the README."
  exit 1
fi

echo
if grep -q '^DISCORD_BOT_TOKEN=replace-me$' .env; then
  echo "Set DISCORD_BOT_TOKEN in .env before starting the bot."
fi

if grep -q '^DISCORD_GUILD_ID=$' .env; then
  echo "DISCORD_GUILD_ID is empty. It is optional, but recommended for development."
fi

echo
echo "Next commands:"
echo "  podman-compose build"
echo "  podman-compose up -d"
echo "  podman-compose logs -f car-watch-bot"
