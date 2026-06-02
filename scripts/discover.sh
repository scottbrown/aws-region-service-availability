#!/usr/bin/env bash
# Discover the list of AWS service endpoint pages from the section's table of contents.
# Output: build/service_pages.txt (one slug per line, e.g. "ses.html")
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="${BUILD_DIR:-$ROOT/build}"
mkdir -p "$BUILD"

TOC_URL="https://docs.aws.amazon.com/general/latest/gr/toc-contents.json"
echo "Fetching TOC: $TOC_URL"
curl -fsS --max-time 30 "$TOC_URL" -o "$BUILD/toc-contents.json"

jq -r '.. | objects | select(.title? == "Service endpoints and quotas") | .contents[]? | .href' \
  "$BUILD/toc-contents.json" | sort -u > "$BUILD/service_pages.txt"

echo "Discovered $(wc -l < "$BUILD/service_pages.txt") service pages -> $BUILD/service_pages.txt"
