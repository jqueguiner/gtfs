#!/usr/bin/env python3
"""
Canada (CA) GTFS feed scraper.

Source
------
Mobility Database (MobilityData) — the de-facto national access point for
Canada. Canada has NO EU-style legally-mandated National Access Point; the
Mobility Database is the freshest machine-readable national compilation
(156 CA GTFS-schedule sources, per-agency JSON with a direct operator
download + an MDB-hosted stable mirror).

We use the UNAUTHENTICATED GitHub catalogs mirror (no Bearer token needed):

  1. Enumerate the repo tree:
       GET https://api.github.com/repos/MobilityData/mobility-database-catalogs
           /git/trees/main?recursive=1
     keep tree[].path starting with
       'catalogs/sources/gtfs/schedule/ca-'   (~156 CA GTFS files).
     Fetched via the `gh` CLI when available (authenticated -> higher rate
     limit / avoids the anonymous 403 some hosts hit), else via urllib.

  2. For each path:
       GET https://raw.githubusercontent.com/MobilityData/
           mobility-database-catalogs/main/<path>
     Read JSON fields:
       provider                         -> operator name
       name                             -> optional sub-feed label ("Express")
       location.subdivision_name        -> province / territory   (subdiv)
       location.municipality            -> city
       location.bounding_box            -> bbox
       urls.direct_download             -> operator zip  (producer_url)
       urls.latest                      -> MDB-hosted stable mirror (hosted_url)
       urls.license                     -> license URL
       status / redirect                -> deprecated sources are skipped

We do NOT touch the federal gtfs_sources.xlsx (its URLs point at the dead
transitfeeds.com). GTFS-Realtime lives in a separate catalogs subtree and is
out of scope here (schedule only).

Each record appended to data/feeds_full.json has EXACTLY these keys:
  id, provider, name, cc, subdiv, city, producer_url, hosted_url,
  license, bbox, status, official
Dedup is by producer_url (rstrip('/')). Stdlib only.
"""

import json
import os
import re
import subprocess
import urllib.request

CC = "CA"
UA = "Mozilla/5.0 (compatible; gtfs-catalog/1.0; +https://github.com/jqueguiner/gtfs)"
TIMEOUT = 60

SRC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "feeds_full.json",
)

REPO = "MobilityData/mobility-database-catalogs"
TREE_API = "https://api.github.com/repos/%s/git/trees/main?recursive=1" % REPO
RAW_BASE = "https://raw.githubusercontent.com/%s/main/" % REPO
PATH_PREFIX = "catalogs/sources/gtfs/schedule/ca-"


def http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def slugify(s):
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "feed"


def list_ca_paths():
    """Return the list of CA GTFS-schedule catalog paths.

    Prefer the authenticated `gh api` (dodges the anonymous GitHub-API 403
    some hosts receive); fall back to a plain urllib GET.
    """
    # 1) gh CLI (authenticated) ------------------------------------------------
    try:
        out = subprocess.run(
            ["gh", "api", "repos/%s/git/trees/main?recursive=1" % REPO,
             "--jq", ".tree[].path"],
            capture_output=True, text=True, timeout=120,
        )
        if out.returncode == 0 and out.stdout.strip():
            paths = [ln.strip() for ln in out.stdout.splitlines()
                     if ln.strip().startswith(PATH_PREFIX)]
            if paths:
                return sorted(set(paths))
    except Exception as e:
        print("  gh api tree failed, falling back to urllib: %s" % e)

    # 2) plain urllib ----------------------------------------------------------
    try:
        data = http_json(TREE_API)
    except Exception as e:
        print("  tree fetch failed: %s" % e)
        return []
    tree = data.get("tree", []) or []
    if data.get("truncated"):
        print("  WARNING: GitHub tree response was truncated")
    return sorted({x["path"] for x in tree
                   if x.get("path", "").startswith(PATH_PREFIX)})


def parse_source(path):
    """Fetch one catalog JSON and return a feed record, or None to skip."""
    try:
        d = http_json(RAW_BASE + path)
    except Exception as e:
        print("  skip %s: %s" % (path, e))
        return None

    # Skip deprecated / redirected sources (dead or superseded feeds).
    status = (d.get("status") or "").lower()
    if status in ("deprecated", "inactive", "development"):
        return None

    urls = d.get("urls", {}) or {}
    producer = (urls.get("direct_download") or "").strip()
    hosted = (urls.get("latest") or "").strip() or None
    # Some sources only have the MDB mirror; use it as producer_url so the
    # feed is still catalogued rather than dropped.
    if not producer:
        producer = hosted or ""
        hosted = None
    if not producer:
        return None

    loc = d.get("location", {}) or {}
    subdiv = loc.get("subdivision_name") or None
    city = loc.get("municipality") or None

    bbox = None
    bb = loc.get("bounding_box")
    if isinstance(bb, dict):
        lo_lon = bb.get("minimum_longitude")
        lo_lat = bb.get("minimum_latitude")
        hi_lon = bb.get("maximum_longitude")
        hi_lat = bb.get("maximum_latitude")
        if None not in (lo_lon, lo_lat, hi_lon, hi_lat):
            bbox = [lo_lon, lo_lat, hi_lon, hi_lat]

    provider = (d.get("provider") or "").strip() or "Unknown operator"
    sub_name = (d.get("name") or "").strip()
    if sub_name:
        title = "%s — %s (GTFS)" % (provider, sub_name)
    else:
        title = "%s (GTFS)" % provider

    lic = (urls.get("license") or "").strip() or None

    # Stable id from the catalog filename (already 'ca-...-gtfs-<id>').
    stem = os.path.splitext(os.path.basename(path))[0]
    fid = slugify(stem)
    if not fid.startswith(CC.lower() + "-"):
        fid = "%s-%s" % (CC.lower(), fid)

    return {
        "id": fid,
        "provider": provider,
        "name": title,
        "cc": CC,
        "subdiv": subdiv,
        "city": city,
        "producer_url": producer,
        "hosted_url": hosted,
        "license": lic,
        "bbox": bbox,
        "status": "active",
        "official": True,
    }


def main():
    try:
        with open(SRC, "r", encoding="utf-8") as fh:
            existing = json.load(fh)
        if not isinstance(existing, list):
            existing = []
    except (FileNotFoundError, ValueError):
        existing = []

    have = set()
    for rec in existing:
        pu = (rec.get("producer_url") or "").rstrip("/")
        if pu:
            have.add(pu)

    paths = list_ca_paths()
    print("  %d CA GTFS-schedule catalog paths" % len(paths))

    added = []
    seen_new = set()
    for p in paths:
        rec = parse_source(p)
        if not rec:
            continue
        pu = (rec.get("producer_url") or "").rstrip("/")
        if not pu or pu in have or pu in seen_new:
            continue
        seen_new.add(pu)
        added.append(rec)

    if added:
        existing.extend(added)
        os.makedirs(os.path.dirname(SRC), exist_ok=True)
        with open(SRC, "w", encoding="utf-8") as fh:
            json.dump(existing, fh, ensure_ascii=False, indent=2)

    print("+%d new %s feeds" % (len(added), CC))


if __name__ == "__main__":
    main()
