#!/usr/bin/env python3
"""Scraper for South Africa (ZA) open-transit GTFS feeds.

South Africa has NO EU-style legally-mandated national access point and NO single
aggregator that enumerates all operators. The national Dept of Transport
(transport.gov.za) publishes no machine-readable feed list. So this scraper
scrapes the two closest *programmatic* catalogs and unions their ZA results:

  (1) DT4A GitLab mirror (gitlab.com/digitaltransport/data/africa)
      Public REST API, no auth. Enumerate the group's projects (each project is a
      city), then walk each repo tree for *.zip files under a "GTFS*" folder. The
      only ZA city currently present is Stellenbosch (minibus-taxi GTFS, collected
      by GoMetro under the DT4A Innovation Challenge). The download URL is a raw
      blob on the project's default branch.

      NOTE: the self-hosted git.digitaltransport4africa.org has an EXPIRED TLS
      cert -- we deliberately use the gitlab.com mirror instead.

  (2) Mobility Database (api.mobilitydatabase.org) -- the cross-operator catalog
      most likely to hold any current ZA feed (e.g. a resurrected MyCiTi entry).
      Its /v1/gtfs_feeds?country_code=ZA endpoint requires a Bearer access token,
      obtained by POSTing a refresh token (free signup) to /v1/tokens. Provide the
      refresh token via env MOBILITYDB_REFRESH_TOKEN (or a ready access token via
      MOBILITYDB_ACCESS_TOKEN). Without a token this source is skipped gracefully;
      the DT4A source still yields the Stellenbosch feed.

Transitland is intentionally NOT used (needs an API key). Cape Town's ArcGIS Hub
(odp-cctegis.opendata.arcgis.com) is GIS shapefile/GeoJSON layers, not a bundled
GTFS zip, so it is skipped for GTFS harvesting.

stdlib only (json, urllib, os, re). Appends records to data/feeds_full.json.
"""
import json
import os
import re
import urllib.request
import urllib.parse
import urllib.error

CC = "ZA"
UA = "gtfs-catalog-scraper/1.0"
TIMEOUT = 60

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'feeds_full.json')

# --- DT4A GitLab mirror ------------------------------------------------------
GL_API = "https://gitlab.com/api/v4"
GL_GROUP = "digitaltransport%2Fdata%2Fafrica"  # url-encoded group path
GL_GROUP_PROJECTS = GL_API + "/groups/" + GL_GROUP + "/projects?include_subgroups=true&per_page=100"
# Which DT4A projects (city repos) are in South Africa. path_with_namespace tail
# (lowercased) -> (subdiv, city). Extend as DT4A adds ZA cities.
DT4A_ZA_CITIES = {
    "stellenbosch": ("Western Cape", "Stellenbosch"),
}
DT4A_LICENSE = "ODbL-1.0"  # DT4A datasets are published under ODbL

# --- Mobility Database -------------------------------------------------------
MDB_BASE = "https://api.mobilitydatabase.org"
MDB_FEEDS = MDB_BASE + "/v1/gtfs_feeds?country_code=" + CC
MDB_TOKENS = MDB_BASE + "/v1/tokens"


def slugify(s):
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def load_existing():
    if not os.path.exists(SRC):
        return []
    try:
        with open(SRC, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (ValueError, OSError):
        return []


def http_json(url, headers=None, data=None, method=None):
    hdrs = {"User-Agent": UA, "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# Source 1: DT4A GitLab mirror
# ---------------------------------------------------------------------------
def scrape_dt4a():
    """Return a list of feed records from ZA city repos on the DT4A GitLab group."""
    records = []
    try:
        projects = http_json(GL_GROUP_PROJECTS)
    except (urllib.error.URLError, ValueError, OSError) as e:
        print("  DT4A: group listing failed:", e)
        return records
    if not isinstance(projects, list):
        return records

    for proj in projects:
        pwn = proj.get("path_with_namespace") or ""
        tail = pwn.rsplit("/", 1)[-1].lower()
        if tail not in DT4A_ZA_CITIES:
            continue
        subdiv, city = DT4A_ZA_CITIES[tail]
        branch = proj.get("default_branch") or "main"
        pid = proj.get("id")
        # List the whole repo tree (recursive) to find GTFS zips.
        tree_url = (GL_API + "/projects/" + str(pid) +
                    "/repository/tree?recursive=true&per_page=100")
        try:
            tree = http_json(tree_url)
        except (urllib.error.URLError, ValueError, OSError) as e:
            print("  DT4A: tree fetch failed for", pwn, ":", e)
            continue
        if not isinstance(tree, list):
            continue

        for entry in tree:
            if entry.get("type") != "blob":
                continue
            path = entry.get("path") or ""
            # Keep *.zip under a top-level folder whose name starts with "GTFS".
            if not path.lower().endswith(".zip"):
                continue
            top = path.split("/", 1)[0]
            if not top.upper().startswith("GTFS"):
                continue

            # Prefer the highest version (…_V3.zip beats _V2/_V1). We record every
            # zip but tag latest; dedup by producer_url keeps them distinct.
            fname = path.rsplit("/", 1)[-1]
            # raw download URL: https://gitlab.com/{pwn}/-/raw/{branch}/{urlenc path}
            enc_path = urllib.parse.quote(path)
            dl = "https://gitlab.com/" + pwn + "/-/raw/" + branch + "/" + enc_path

            ver_m = re.search(r"_V(\d+)", fname, re.I)
            ver = int(ver_m.group(1)) if ver_m else 0
            base = re.sub(r"\.zip$", "", fname, flags=re.I)
            provider = city + " minibus taxis (GoMetro / DT4A)"
            title = "GTFS — " + base + " (DT4A / GoMetro)"
            fid = CC.lower() + "-" + slugify(city) + "-dt4a-" + slugify(base)
            records.append({
                "_ver": ver, "_city": city.lower(),
                "record": {
                    "id": fid,
                    "provider": provider,
                    "name": title,
                    "cc": CC,
                    "subdiv": subdiv,
                    "city": city,
                    "producer_url": dl,
                    "hosted_url": None,
                    "license": DT4A_LICENSE,
                    "bbox": None,
                    "status": "active",
                    "official": True,
                },
            })

    # Keep only the latest version per city (drop older V1/V2 zips).
    best = {}
    for r in records:
        c = r["_city"]
        if c not in best or r["_ver"] > best[c]["_ver"]:
            best[c] = r
    return [r["record"] for r in best.values()]


# ---------------------------------------------------------------------------
# Source 2: Mobility Database
# ---------------------------------------------------------------------------
def mdb_access_token():
    tok = os.environ.get("MOBILITYDB_ACCESS_TOKEN")
    if tok:
        return tok.strip()
    refresh = os.environ.get("MOBILITYDB_REFRESH_TOKEN")
    if not refresh:
        return None
    try:
        resp = http_json(MDB_TOKENS, data={"refresh_token": refresh.strip()}, method="POST")
        return resp.get("access_token")
    except (urllib.error.URLError, ValueError, OSError) as e:
        print("  MobilityDB: token exchange failed:", e)
        return None


def scrape_mobilitydb():
    """Return a list of feed records for ZA from the Mobility Database, if a token
    is available. Skips gracefully (returns []) when no token / on error."""
    records = []
    token = mdb_access_token()
    if not token:
        print("  MobilityDB: no token (set MOBILITYDB_REFRESH_TOKEN or "
              "MOBILITYDB_ACCESS_TOKEN) -- skipping this source")
        return records
    try:
        feeds = http_json(MDB_FEEDS, headers={"Authorization": "Bearer " + token})
    except (urllib.error.URLError, ValueError, OSError) as e:
        print("  MobilityDB: feed query failed:", e)
        return records
    if not isinstance(feeds, list):
        return records

    for f in feeds:
        if not isinstance(f, dict):
            continue
        # Skip deprecated / redirected feeds.
        status = (f.get("status") or "active").lower()
        if status == "deprecated":
            continue
        if f.get("redirects"):
            continue

        source_info = f.get("source_info") or {}
        latest = f.get("latest_dataset") or {}
        producer = source_info.get("producer_url")
        hosted = latest.get("hosted_url")
        # Need a real GTFS zip URL. Prefer producer_url (direct from operator),
        # fall back to MobilityData-hosted mirror.
        url = producer or hosted
        if not url:
            continue

        locs = f.get("locations") or []
        loc = locs[0] if locs else {}
        # Guard: only keep ZA (defensive; the query already filters by country).
        if (loc.get("country_code") or CC).upper() != CC:
            continue
        subdiv = loc.get("subdivision_name")
        city = loc.get("municipality")

        provider = f.get("provider") or "Unknown operator"
        feed_name = f.get("feed_name")
        title = feed_name or ("GTFS — " + provider)
        mdb_id = f.get("id") or slugify(provider)
        fid = CC.lower() + "-mdb-" + slugify(mdb_id)

        records.append({
            "id": fid,
            "provider": provider,
            "name": title,
            "cc": CC,
            "subdiv": subdiv or None,
            "city": city or None,
            "producer_url": url,
            "hosted_url": hosted if url == producer else None,
            "license": None,
            "bbox": None,
            "status": "active",
            "official": bool(f.get("official", True)),
        })
    return records


def main():
    existing = load_existing()
    seen = set()
    for r in existing:
        pu = r.get("producer_url")
        if pu:
            seen.add(pu.rstrip("/"))

    print("Scraping ZA (South Africa) -- no NAP; unioning DT4A GitLab + Mobility Database")
    print(" [1] DT4A GitLab mirror")
    dt4a = scrape_dt4a()
    print("     found", len(dt4a), "DT4A feed(s)")
    print(" [2] Mobility Database")
    mdb = scrape_mobilitydb()
    print("     found", len(mdb), "MobilityDB feed(s)")

    added = 0
    for rec in dt4a + mdb:
        pu = rec.get("producer_url")
        if not pu:
            continue
        key = pu.rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        existing.append(rec)
        added += 1

    if added:
        with open(SRC, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

    print("+%d new %s feeds" % (added, CC))


if __name__ == "__main__":
    main()
