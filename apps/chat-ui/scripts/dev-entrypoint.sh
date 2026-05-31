#!/bin/sh

set -eu

cd /app

LOCKFILE="package-lock.json"
STAMP_FILE="node_modules/.package-lock.sha256"

if [ ! -f "$LOCKFILE" ]; then
  echo "Missing $LOCKFILE" >&2
  exit 1
fi

CURRENT_HASH="$(sha256sum "$LOCKFILE" | awk '{ print $1 }')"
INSTALLED_HASH=""

if [ -f "$STAMP_FILE" ]; then
  INSTALLED_HASH="$(cat "$STAMP_FILE")"
fi

if [ ! -d node_modules ] || [ "$CURRENT_HASH" != "$INSTALLED_HASH" ]; then
  echo "Installing chat-ui dependencies..."
  npm ci
  mkdir -p "$(dirname "$STAMP_FILE")"
  printf '%s' "$CURRENT_HASH" > "$STAMP_FILE"
fi

exec npm run dev -- --webpack --hostname 0.0.0.0
