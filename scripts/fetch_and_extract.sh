#!/usr/bin/env bash
# Download all service endpoint pages (parallel) and run the deterministic extractor.
# Inputs:  build/service_pages.txt
# Outputs: build/pages/<slug> (raw html cache), build/endpoints-extracted.jsonl
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="${BUILD_DIR:-$ROOT/build}"
BASE="https://docs.aws.amazon.com/general/latest/gr"
mkdir -p "$BUILD/pages"
: > "$BUILD/endpoints-extracted.jsonl"

fetch_one() {
  local slug="$1" out="$BUILD/pages/$1"
  if [ ! -s "$out" ]; then
    curl -fsS --max-time 30 "$BASE/$slug" -o "$out" || echo "WARN: failed $slug" >&2
  fi
}
export -f fetch_one
export BASE BUILD

echo "Downloading $(wc -l < "$BUILD/service_pages.txt") pages…"
xargs -P 12 -I{} bash -c 'fetch_one "$@"' _ {} < "$BUILD/service_pages.txt"

echo "Extracting endpoint tables…"
n=0
while IFS= read -r slug; do
  [ -s "$BUILD/pages/$slug" ] || { echo "MISSING: $slug" >&2; continue; }
  python3 "$ROOT/scripts/extract_endpoints.py" "$slug" < "$BUILD/pages/$slug" \
    | jq -c '.' >> "$BUILD/endpoints-extracted.jsonl"
  n=$((n+1))
done < "$BUILD/service_pages.txt"
echo "Extracted $n pages -> $BUILD/endpoints-extracted.jsonl"
