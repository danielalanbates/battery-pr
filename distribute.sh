#!/bin/bash
# distribute.sh — Build, sign, notarize, and package Battery for distribution
# electron-builder + afterSign.js handle signing and notarization automatically.
#
# CI usage (pass via env):
#   APPLEID=you@example.com APPLEIDPASS=xxxx TEAMID=XXXXXXXXXX ./distribute.sh
#
# Required env vars for afterSign.js notarization:
#   APPLEID        — Apple ID email
#   APPLEIDPASS    — app-specific password from appleid.apple.com
#   TEAMID         — 10-char team ID

set -euo pipefail
cd "$(dirname "$0")/app"

echo "📦  Installing dependencies…"
npm ci

echo "🔨  Building Battery (Electron)…"
# Build universal binary for both Apple Silicon and Intel
npm run build -- --mac --universal

DMG=$(find dist -name "*.dmg" | head -1)
if [ -z "$DMG" ]; then
  echo "❌  No DMG found in app/dist/"
  exit 1
fi

mkdir -p ../dist
cp "$DMG" ../dist/

echo ""
echo "🎉  $(basename "$DMG")"
afplay /System/Library/Sounds/Glass.aiff 2>/dev/null || true
