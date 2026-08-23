#!/usr/bin/env bash
# Hourly: refresh the catalog from every open source, rebuild, push if changed,
# then email jlq@ the coverage delta vs last hour. Cron: 0 * * * *
set -uo pipefail
REPO="${GTFS_REPO:-/home/ubuntu/gtfs}"   # persistent local clone
LOG=/tmp/gtfs_hourly.log
# Email runs on a100 (Resend env + mailer live there); we scp the html + ssh.
cd "$REPO" || exit 1
[ -f /home/ubuntu/.config/gtfs/env ] && . /home/ubuntu/.config/gtfs/env
{
echo "=== $(date -u) hourly refresh ==="

# latest code + snapshot
git pull --quiet --ff-only 2>&1 | tail -1 || true

# refresh feeds from the fast open sources (MDB needs a token -> optional)
[ -n "${MDB_REFRESH_TOKEN:-}" ] && python3 scripts/ingest_mdb.py || true
if [ -d /tmp/transitland-atlas ]; then git -C /tmp/transitland-atlas pull --quiet || true; \
  else git clone --depth 1 --quiet https://github.com/transitland/transitland-atlas.git /tmp/transitland-atlas || true; fi
python3 scripts/scrape_transitland.py /tmp/transitland-atlas || true
python3 scripts/scrape_france.py || true
python3 scripts/scrape_de.py || true
for s in scripts/scrape_*.py; do
  case "$s" in *france*|*transitland*|*_de.py) ;; *) timeout 200 python3 "$s" || true;; esac
done
timeout 600 python3 scripts/resolve_unplaced.py 300 || true

# autonomous per-country growth: re-split national NAP feeds (deterministic, no LLM)
timeout 400 python3 scripts/split_national.py || true

# rebuild tree + coverage table
python3 scripts/build_repo.py || true

# autonomous gap report: worst per-country deficits (drives next synth targets)
python3 scripts/coverage_gaps.py 15 > /tmp/gtfs_gaps.json 2>/dev/null || true

# compute the delta (writes /tmp/gtfs_delta.html, updates snapshot)
SUBJECT=$(python3 scripts/report_delta.py)
# email via a100 (Resend env + mailer live there)
scp -q /tmp/gtfs_delta.html a100:/tmp/gtfs_delta.html \
  && ssh a100 "python3 /data/addresses/agent/mailer.py \"$SUBJECT\" /tmp/gtfs_delta.html jl@gladia.io" || true

# commit + push if the catalog changed
if ! git diff --quiet; then
  git add -A
  git commit -q -m "hourly refresh: ${SUBJECT}" || true
  TOK=$(gh auth token 2>/dev/null)
  [ -n "$TOK" ] && git push --quiet "https://x-access-token:${TOK}@github.com/jqueguiner/gtfs.git" HEAD:main || git push --quiet || true
fi
echo "done: $SUBJECT"
} >> "$LOG" 2>&1
