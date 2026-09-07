#!/bin/sh
set -eu

api_key_file=/app/api_key_journal_unitech.txt

if [ -z "${TELEGRAM_API_KEY:-}" ]; then
    echo "TELEGRAM_API_KEY is not set" >&2
    exit 1
fi

umask 077
printf '%s\n' "$TELEGRAM_API_KEY" > "$api_key_file"

exec "$@"
