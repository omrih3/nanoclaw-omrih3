#!/usr/bin/env bash
# Interactively add a Telegram bot instance to .env.
# Asks for a name (e.g. "receipts") and the BotFather token (hidden input), then sets
# TELEGRAM_BOT_TOKEN_<NAME> and appends <name> to TELEGRAM_INSTANCES.
# The token is never printed. Restart the service afterwards.
set -euo pipefail
cd "$(dirname "$0")/.."
ENV_FILE=".env"
touch "$ENV_FILE"

read -r -p "Bot instance name (letters/digits/_, e.g. receipts): " name
name="$(printf '%s' "$name" | tr 'A-Z' 'a-z')"
[[ "$name" =~ ^[a-z][a-z0-9_]*$ ]] || { echo "Invalid name." >&2; exit 1; }
key="TELEGRAM_BOT_TOKEN_$(printf '%s' "$name" | tr 'a-z' 'A-Z')"

read -r -s -p "Bot token from @BotFather (input hidden): " token; echo
[[ "$token" =~ ^[0-9]+:[A-Za-z0-9_-]{30,}$ ]] || { echo "That doesn't look like a Telegram bot token." >&2; exit 1; }

# Each bot needs its own token (Telegram allows one poller per token).
if grep -E '^TELEGRAM_BOT_TOKEN[A-Z_]*=' "$ENV_FILE" | grep -v "^$key=" | cut -d= -f2- | grep -qxF "$token"; then
  echo "That token is already used by another bot in .env." >&2; exit 1
fi

if existing="$(grep -E "^$key=" "$ENV_FILE" || true)" && [ -n "$existing" ]; then
  read -r -p "$key already exists. Overwrite? [y/N] " yn
  [[ "$yn" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 0; }
fi

# Optional check against Telegram (token goes only to api.telegram.org).
if command -v curl >/dev/null; then
  if resp="$(curl -fsS --max-time 10 "https://api.telegram.org/bot${token}/getMe" 2>/dev/null)"; then
    echo "Telegram accepted the token: @$(printf '%s' "$resp" | sed -n 's/.*"username":"\([^"]*\)".*/\1/p')"
  else
    read -r -p "Telegram rejected the token or is unreachable. Save anyway? [y/N] " yn
    [[ "$yn" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 1; }
  fi
fi

cp "$ENV_FILE" "$ENV_FILE.bak"
grep -v -E "^$key=" "$ENV_FILE.bak" > "$ENV_FILE" || true
printf '%s=%s\n' "$key" "$token" >> "$ENV_FILE"

cur="$(sed -n 's/^TELEGRAM_INSTANCES=//p' "$ENV_FILE" | head -1)"
new="$({ printf '%s\n' "$cur" | tr ',' '\n'; echo "$name"; } | grep . | sort -u | paste -sd, -)"
grep -v -E '^TELEGRAM_INSTANCES=' "$ENV_FILE" > "$ENV_FILE.tmp" || true
printf 'TELEGRAM_INSTANCES=%s\n' "$new" >> "$ENV_FILE.tmp"
mv "$ENV_FILE.tmp" "$ENV_FILE"
chmod 600 "$ENV_FILE"; rm -f "$ENV_FILE.bak"

echo "Saved $key. TELEGRAM_INSTANCES=$new"
echo "Next: restart the service (bash setup/lib/restart.sh) and tell Claude it's done."
