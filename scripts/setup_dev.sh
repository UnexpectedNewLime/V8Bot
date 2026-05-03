#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

missing_tools=()

get_env_value() {
  local key="$1"
  local line

  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" == "$key="* ]]; then
      printf '%s' "${line#*=}"
      return
    fi
  done < .env
}

set_env_value() {
  local key="$1"
  local value="$2"
  local tmp_file
  local found=0
  local line

  tmp_file="$(mktemp)"

  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" == "$key="* ]]; then
      printf '%s=%s\n' "$key" "$value" >> "$tmp_file"
      found=1
    else
      printf '%s\n' "$line" >> "$tmp_file"
    fi
  done < .env

  if [[ "$found" -eq 0 ]]; then
    printf '%s=%s\n' "$key" "$value" >> "$tmp_file"
  fi

  mv "$tmp_file" .env
}

prompt_env_value() {
  local key="$1"
  local placeholder="$2"
  local prompt="$3"
  local current_value
  local new_value

  current_value="$(get_env_value "$key")"

  if [[ -n "$current_value" && "$current_value" != "$placeholder" ]]; then
    echo "$key is already set; leaving it unchanged."
    return
  fi

  if ! read -r -p "$prompt (leave blank to skip): " new_value; then
    echo
    new_value=""
  fi

  if [[ -n "$new_value" ]]; then
    set_env_value "$key" "$new_value"
    echo "Updated $key in .env."
  else
    echo "Skipped $key."
  fi
}

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

echo
prompt_env_value "DISCORD_BOT_TOKEN" "replace-me" "Enter your Discord bot token"
prompt_env_value "DISCORD_GUILD_ID" "" "Enter your Discord guild ID"

if ((${#missing_tools[@]} > 0)); then
  echo
  echo "Missing required Podman tooling: ${missing_tools[*]}"
  echo "Install the missing tool(s), then rerun this script or continue with the README."
  exit 1
fi

echo
echo "Next commands:"
echo "  podman-compose build"
echo "  podman-compose up -d"
echo "  podman-compose logs -f car-watch-bot"
