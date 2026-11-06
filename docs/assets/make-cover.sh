#!/usr/bin/env bash
# Regenerates docs/assets/cover.png (the repository cover / GitHub social preview, 1280x640)
# from docs/assets/cover.html, which lays out the icon, name and docs/assets/openfinance-screenshot.png.
#
#   docs/assets/make-cover.sh
#
# Needs Google Chrome (or set CHROME to any Chromium binary).
set -euo pipefail

root="$(cd "$(dirname "$0")/../.." && pwd)"
chrome="${CHROME:-}"
for candidate in "$chrome" google-chrome google-chrome-stable chromium chromium-browser \
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"; do
  [ -n "$candidate" ] && command -v "$candidate" >/dev/null 2>&1 && { chrome="$candidate"; break; }
done
[ -n "$chrome" ] || { echo "Google Chrome not found; set CHROME=/path/to/chrome" >&2; exit 1; }

"$chrome" --headless=new --no-sandbox --disable-gpu --hide-scrollbars --force-device-scale-factor=1 \
  --window-size=1280,640 --screenshot="$root/docs/assets/cover.png" "file://$root/docs/assets/cover.html"
echo "wrote docs/assets/cover.png"
