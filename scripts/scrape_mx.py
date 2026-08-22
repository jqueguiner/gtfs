#!/usr/bin/env python3
"""
Mexico (MX) GTFS feed scraper.

Aggregator landscape
--------------------
Mexico has NO EU-style National Access Point. datos.gob.mx (the national open-data
portal) hosts only railway statistics/infrastructure - no GTFS. The *de-facto*
national access point is the Mobility Database (MDB), which already catalogs the
main MX producers (CDMX/SEMOVI, Jalisco/SITEUR "Mi Transporte", Aguascalientes/
CMOV, ...). Underneath MDB, the actual open GTFS lives on independent state/city
CKAN portals that we scrape directly to EXCEED the MDB catalog:

  * CDMX     -> https://datos.cdmx.gob.mx      (SEMOVI/ADIP consolidated feed)
  * Jalisco  -> https://datos.jalisco.gob.mx   (SITEUR / Mi Transporte)

Most other MX cities have no published open GTFS (informal / concessioned microbus
networks). Monterrey (Metrorrey), Puebla (RUTA) and others have no confirmed
official feed - if MDB happens to expose one, we pick it up automatically.

Sources, in priority order
--------------------------
1. Mobility Database API  (GET /v1/gtfs_feeds?country_code=MX)
     - Auth: Bearer access token. A free MDB account gives a long-lived
       *refresh token*; POST it to /v1/tokens to mint a 1-hour access token.
       Supply it via env MDB_REFRESH_TOKEN (or MOBILITY_DATABASE_REFRESH_TOKEN).
     - Each feed -> source_info.producer_url (upstream, authoritative) is used as
       producer_url; latest_dataset.hosted_url is the MDB-hosted mirror. We prefer
       producer_url and fall back to the hosted mirror only when the upstream URL
       is missing.
     - If no token is configured (or the API is unreachable), this source is
       skipped and we still emit the CKAN + seed feeds below.

2. State CKAN portals  (CDMX, Jalisco) via the CKAN action API
     - package_show?id=<known dataset>  -> the canonical GTFS zip for that portal
     - package_search?q=gtfs            -> any other GTFS zips the portal exposes
       (future-proofing; portals rename/add datasets over time)
     - The live download filename is resolved from result.resources[] at run time
       (never hardcoded) because CDMX/Jalisco date-stamp or re-version the zips.

3. Seed feeds  (last-resort, verified direct zips)
     - The current CDMX SEMOVI consolidated GTFS direct zip is included as a seed
       so the catalog still gains the single most important MX feed even when both
       the MDB API and the CKAN portals are unreachable (they geo/WAF-block some
       networks). Dedup by producer_url guarantees no double-count when the CKAN
       scrape also resolves it.

Each record appended to data/feeds_full.json has EXACTLY these keys:
  id, provider, name, cc, subdiv, city, producer_url, hosted_url,
  license, bbox, status, official
Dedup is by producer_url (rstrip('/')). Stdlib only (json, urllib, os, re).
"""

import json
import os
import re
import urllib.request

CC = "MX"
UA = "Mozilla/5.0 (compatible; gtfs-catalog/1.0; +https://github.com/jqueguiner/gtfs)"
TIMEOUT = 60

SRC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "feeds_full.json",
)

# --- Mobility Database (de-facto national access point) ---------------------
MDB_API = "https://api.mobilitydatabase.org"
MDB_TOKENS = MDB_API + "/v1/tokens"
MDB_FEEDS = MDB_API + "/v1/gtfs_feeds?country_code=%s&limit=%d&offset=%d"
MDB_PAGE = 200
MDB_REFRESH_TOKEN = (
    os.environ.get("MDB_REFRESH_TOKEN")
    or os.environ.get("MOBILITY_DATABASE_REFRESH_TOKEN")
    or os.environ.get("MOBILITYDATABASE_REFRESH_TOKEN")
)

# --- State CKAN portals ------------------------------------------------------
CKAN_PORTALS = [
    {
        "base": "https://datos.cdmx.gob.mx",
        "subdiv": "Ciudad de Mexico",
        "city": "Mexico City",
        # SEMOVI / ADIP consolidated static GTFS (Metro, Metrobus, Trolebus/STE,
        # Tren Ligero, RTP, Cablebus, Tren Suburbano, corredores, Pumabus).
        "dataset_ids": ["gtfs"],
    },
    {
        "base": "https://datos.jalisco.gob.mx",
        "subdiv": "Jalisco",
        "city": "Guadalajara",
        # SITEUR / Mi Transporte (MiMacro BRT, MiTren, SiTren, Tren Ligero L1-L3).
        "dataset_ids": [
            "actualizacion-de-rutas-de-transporte-publico-colectivo-y-"
            "masivo-en-la-zona-metropolitana-de"
        ],
    },
]

# --- Seed feeds (verified direct zips, used as a floor) ----------------------
SEED_FEEDS = [
    {
        "id": "mx-cdmx-semovi-gtfs",
        "provider": "SEMOVI / ADIP (Gobierno de la Ciudad de Mexico)",
        "name": "GTFS CDMX consolidated (Metro, Metrobus, Trolebus/STE, "
                "Tren Ligero, RTP, Cablebus, Tren Suburbano, corredores "
                "concesionados, Pumabus)",
        "cc": CC,
        "subdiv": "Ciudad de Mexico",
        "city": "Mexico City",
        "producer_url": "https://datos.cdmx.gob.mx/dataset/"
                        "75538d96-3ade-4bc5-ae7d-d85595e4522d/resource/"
                        "32ed1b6b-41cd-49b3-b7f0-b57acb0eb819/download/gtfs-2.zip",
        "hosted_url": None,
        "license": None,
        "bbox": None,
        "status": "active",
        "official": True,
    },
]

# CKAN license_id -> human/SPDX-ish label.
LICENSE_MAP = {
    "cc-by": "CC-BY-4.0",
    "cc-by-4.0": "CC-BY-4.0",
    "cc-zero": "CC0-1.0",
    "cc-by-sa": "CC-BY-SA-4.0",
    "odc-by": "ODC-BY-1.0",
    "odc-odbl": "ODbL-1.0",
    "notspecified": None,
    "": None,
    None: None,
}


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
        return json.loads(r.read().decode("utf-8", "replace"))


def slugify(s):
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "feed"


def clean(s):
    if not s:
        return None
    s = str(s).strip()
    return s or None


# ---------------------------------------------------------------------------
# Source 1: Mobility Database
# ---------------------------------------------------------------------------
def mdb_access_token():
    """Mint a 1-hour access token from the configured refresh token, or None."""
    if not MDB_REFRESH_TOKEN:
        print("  MDB: no refresh token in env "
              "(MDB_REFRESH_TOKEN) -> skipping MDB API")
        return None
    try:
        resp = http_json(MDB_TOKENS, data={"refresh_token": MDB_REFRESH_TOKEN},
                         method="POST")
    except Exception as e:
        print("  MDB: token request failed: %s" % e)
        return None
    tok = resp.get("access_token") or resp.get("accessToken")
    if not tok:
        print("  MDB: token response missing access_token")
        return None
    return tok


def mdb_bbox(feed):
    """Build [W,S,E,N] from latest_dataset.bounding_box or feed.bounding_box."""
    bb = (feed.get("latest_dataset") or {}).get("bounding_box") \
        or feed.get("bounding_box") or {}
    try:
        w = bb.get("minimum_longitude")
        s = bb.get("minimum_latitude")
        e = bb.get("maximum_longitude")
        n = bb.get("maximum_latitude")
        if None in (w, s, e, n):
            return None
        return [float(w), float(s), float(e), float(n)]
    except (TypeError, ValueError):
        return None


def mdb_license(feed):
    si = feed.get("source_info") or {}
    lid = clean(si.get("license_id"))
    if lid:
        m = LICENSE_MAP.get(lid.lower(), lid)
        if m:
            return m
    return clean(si.get("license_url"))


def scrape_mdb():
    """Yield feed records from the Mobility Database for country_code=MX."""
    token = mdb_access_token()
    if not token:
        return
    hdrs = {"Authorization": "Bearer %s" % token}
    offset = 0
    total = 0
    while True:
        url = MDB_FEEDS % (CC, MDB_PAGE, offset)
        try:
            feeds = http_json(url, headers=hdrs)
        except Exception as e:
            print("  MDB: gtfs_feeds fetch failed (offset %d): %s" % (offset, e))
            break
        if not isinstance(feeds, list):
            # Some deployments wrap the list; be tolerant.
            feeds = feeds.get("results") if isinstance(feeds, dict) else None
            if not isinstance(feeds, list):
                break
        if not feeds:
            break
        for feed in feeds:
            si = feed.get("source_info") or {}
            latest = feed.get("latest_dataset") or {}
            producer = clean(si.get("producer_url"))
            hosted = clean(latest.get("hosted_url"))
            # Prefer the upstream producer URL; fall back to the MDB mirror.
            purl = producer or hosted
            if not purl:
                continue
            locs = feed.get("locations") or []
            loc0 = locs[0] if locs else {}
            subdiv = clean(loc0.get("subdivision_name"))
            city = clean(loc0.get("municipality"))
            provider = clean(feed.get("provider")) or "Unknown operator"
            name = clean(feed.get("feed_name")) or provider
            mdb_id = clean(feed.get("id"))
            slug = slugify(mdb_id or provider)
            status = clean(feed.get("status")) or "active"
            if status not in ("active", "inactive", "deprecated",
                              "development", "future"):
                status = "active"
            official = feed.get("official")
            official = True if official is None else bool(official)
            total += 1
            yield {
                "id": "%s-%s" % (CC.lower(), slug),
                "provider": provider,
                "name": name,
                "cc": CC,
                "subdiv": subdiv,
                "city": city,
                "producer_url": purl,
                "hosted_url": hosted if hosted and hosted != purl else None,
                "license": mdb_license(feed),
                "bbox": mdb_bbox(feed),
                "status": status if status == "active" else "active",
                "official": official,
            }
        if len(feeds) < MDB_PAGE:
            break
        offset += MDB_PAGE
    print("  MDB: %d MX feeds seen" % total)


# ---------------------------------------------------------------------------
# Source 2: state CKAN portals
# ---------------------------------------------------------------------------
def is_gtfs_resource(res):
    """True if a CKAN resource looks like a direct GTFS zip download."""
    url = (res.get("url") or "").strip()
    if not url:
        return False
    fmt = (res.get("format") or "").lower()
    name = (res.get("name") or "").lower()
    low = url.lower()
    if fmt == "gtfs":
        return low.endswith(".zip") or "gtfs" in low
    if not low.endswith(".zip"):
        return False
    return "gtfs" in name or "gtfs" in low or "gtfs" in fmt


def find_gtfs_url(pkg):
    for res in pkg.get("resources", []) or []:
        if is_gtfs_resource(res):
            return res["url"].strip()
    return None


def ckan_license(pkg):
    lid = (pkg.get("license_id") or "").lower()
    if lid in LICENSE_MAP:
        return LICENSE_MAP[lid]
    return clean(pkg.get("license_title")) or (clean(pkg.get("license_id")))


def emit_ckan_pkg(portal, pkg):
    zurl = find_gtfs_url(pkg)
    if not zurl:
        return None
    name_ds = pkg.get("name") or pkg.get("id")
    title = pkg.get("title") or name_ds
    org = (pkg.get("organization") or {}).get("title")
    return {
        "id": "%s-%s" % (CC.lower(), slugify(name_ds)),
        "provider": clean(org) or clean(title) or "Unknown operator",
        "name": clean(title) or name_ds,
        "cc": CC,
        "subdiv": portal["subdiv"],
        "city": portal["city"],
        "producer_url": zurl,
        "hosted_url": None,
        "license": ckan_license(pkg),
        "bbox": None,
        "status": "active",
        "official": True,
    }


def scrape_ckan_portal(portal):
    base = portal["base"]
    # (a) known datasets via package_show
    for did in portal["dataset_ids"]:
        url = "%s/api/3/action/package_show?id=%s" % (base, did)
        try:
            data = http_json(url)
        except Exception as e:
            print("  CKAN %s package_show(%s) failed: %s" % (base, did, e))
            continue
        pkg = data.get("result") or {}
        rec = emit_ckan_pkg(portal, pkg)
        if rec:
            yield rec
        else:
            print("  CKAN %s: no GTFS resource in dataset '%s'" % (base, did))

    # (b) generic discovery via package_search?q=gtfs
    url = "%s/api/3/action/package_search?q=gtfs&rows=100" % base
    try:
        data = http_json(url)
    except Exception as e:
        print("  CKAN %s package_search failed: %s" % (base, e))
        return
    for pkg in (data.get("result") or {}).get("results", []) or []:
        rec = emit_ckan_pkg(portal, pkg)
        if rec:
            yield rec


def scrape_ckan():
    for portal in CKAN_PORTALS:
        try:
            for rec in scrape_ckan_portal(portal):
                yield rec
        except Exception as e:
            print("  CKAN %s errored: %s" % (portal["base"], e))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
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

    added = []
    seen_new = set()
    # MDB first (richest metadata), then live CKAN, then verified seeds.
    for rec in list(scrape_mdb()) + list(scrape_ckan()) + list(SEED_FEEDS):
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
