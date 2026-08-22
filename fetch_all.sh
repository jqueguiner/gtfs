#!/usr/bin/env sh
# Download every operator's GTFS by running each fetch.sh.
# Usage: ./fetch_all.sh [COUNTRY]   e.g. ./fetch_all.sh FR
ROOT="$(CDPATH= cd "$(dirname "$0")" && pwd)"; CC="${1:-}"
find "$ROOT/$CC" -name fetch.sh 2>/dev/null | while read s; do sh "$s" || true; done
