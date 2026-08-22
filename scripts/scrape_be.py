#!/usr/bin/env python3
"""
Scraper: Belgium (BE) — transportdata.be (Belgian National Access Point, CKAN).

transportdata.be is Belgium's legally-mandated National Access Point (EU ITS
Directive): a CKAN metadata catalogue, browsable/machine-readable with no login.
We query its package_search action for GTFS and iterate the resources.

CKAN response shape (verified):
  {"help":..,"success":true,
   "result":{"count":8,"results":[
       {"title":"TEC GTFS","name":"tec-gtfs",
        "organization":{"title":"TEC",..},
        "license_title":"CC Zero","license_id":"cc-zero",
        "resources":[{"format":"GTFS"|"gtfs-rt"|..,"url":"http..zip"|"..#api"}, ..]},
       ..]}}

Strategy:
  * Pull result.results[].resources[]; take resource.url when the resource is a
    STATIC GTFS zip: format contains 'gtfs' (not RT) AND url ends with '.zip'
    (drops GTFS-RT .bin/.json and the api-details# portal pages CKAN lists for
    De Lijn & STIB). This dynamically catches TEC, Eurostar, DeWaterbus.
  * Belgium has NO city operators: 3 regional nets (De Lijn=Flanders,
    STIB=Brussels, TEC=Wallonia) + SNCB national rail. De Lijn & STIB expose
    only key/OAuth-gated endpoints (CKAN lists just their portal landing page),
    and SNCB's CKAN entry points at a landing page, so we hardcode the 4 core
    verified file URLs plus 2 niche feeds (Eurostar, DeWaterbus) as
    outage-proof fallbacks. Merge with the CKAN mine + dedup by producer_url.

Endpoints for De Lijn / STIB need free credentials (Ocp-Apim-Subscription-Key /
OAuth2 client_credentials); we record the canonical file URL as producer_url.

stdlib only (json, urllib, os, re). Appends to data/feeds_full.json, dedup by
producer_url (rstrip('/')). Prints '+N new BE feeds'.
"""

import json
import os
import re
import urllib.request
import urllib.error

SRC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "feeds_full.json",
)

CC = "BE"
TIMEOUT = 30
API_URL = "https://transportdata.be/api/3/action/package_search?q=GTFS&rows=200"
HEADERS = {
    "User-Agent": "adresses-gtfs-catalog/1.0 (+https://github.com/jqueguiner/gtfs)",
    "Accept": "application/json",
}

# ---------------------------------------------------------------------------
# The 4 core Belgian networks (whole-country coverage) + verified niche feeds.
# CKAN lists De Lijn & STIB only as key-gated portal pages, so their canonical
# file URLs are hardcoded here (verified). SNCB direct zip is hardcoded too
# because CKAN points at the belgiantrain.be landing page, not the file.
# Niche feeds (Eurostar, DeWaterbus) are also hardcoded so they survive a
# transient CKAN outage; collect_from_ckan() dedups the overlap.
# subdiv / city per-operator; regional feeds carry the region, not a city.
# ---------------------------------------------------------------------------
CORE = [
    {
        "slug": "sncb-nmbs",
        "provider": "SNCB / NMBS",
        "name": "SNCB/NMBS national rail GTFS (all Belgian stations, incl. cross-border)",
        "subdiv": None,
        "city": None,
        "url": "https://gtfs.irail.be/nmbs/gtfs/latest.zip",
        "license": "CC0-1.0",
    },
    {
        "slug": "tec-otw",
        "provider": "TEC (Operateur de Transport de Wallonie)",
        "name": "TEC GTFS (all Wallonia: Charleroi, Liege, Namur, Mons, ...)",
        "subdiv": "Wallonia",
        "city": None,
        "url": "https://opendata.tec-wl.be/Current%20GTFS/TEC-GTFS.zip",
        "license": "CC0-1.0",
    },
    {
        "slug": "de-lijn",
        "provider": "De Lijn (Vlaamse Vervoermaatschappij)",
        "name": "De Lijn GTFS Static v3 (all Flanders bus+tram)",
        "subdiv": "Flanders",
        "city": None,
        # GTFS-Static-v3 API — needs a free Ocp-Apim-Subscription-Key.
        "url": "https://api.delijn.be/gtfs/static/v3/gtfs_transit.zip",
        "license": "ODbL-1.0",
    },
    {
        "slug": "stib-mivb",
        "provider": "STIB-MIVB",
        "name": "STIB-MIVB GTFS (Brussels-Capital metro+tram+bus)",
        "subdiv": "Brussels-Capital",
        "city": "Brussels",
        # OAuth2 client_credentials (POST /token) then Bearer GET this file.
        "url": "https://opendata-api.stib-mivb.be/Files/1.0/Gtfs",
        "license": None,
    },
    # Niche feeds also listed in CKAN as direct zips; hardcoded as a fallback so
    # they survive a transient CKAN outage (collect_from_ckan dedups the overlap).
    {
        "slug": "eurostar",
        "provider": "Eurostar",
        "name": "Eurostar GTFS (international HS rail: Brussels-London/Paris/Amsterdam)",
        "subdiv": None,
        "city": None,
        "url": "https://integration-storage.dm.eurostar.com/gtfs-prod/gtfs_static_commercial_v2.zip",
        "license": None,
    },
    {
        "slug": "dewaterbus",
        "provider": "DeWaterbus",
        "name": "DeWaterbus GTFS (Scheldt waterbus/ferry around Antwerp)",
        "subdiv": "Flanders",
        "city": "Antwerp",
        "url": "http://addtransit.com/gtfsfile/85165/DeWaterbus.zip",
        "license": None,
    },
]


def slugify(s):
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def load_existing():
    try:
        with open(SRC, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except (FileNotFoundError, ValueError):
        pass
    return []


def http_get_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception:
        return None


def is_static_gtfs_zip(res):
    """A resource is a static GTFS zip if its format says GTFS (not RT) and the
    URL ends in .zip. Drops GTFS-RT (.bin/.json) and api-details# portal pages."""
    fmt = (res.get("format") or "").strip().lower()
    url = (res.get("url") or "").strip()
    if not url or "#" in url:
        return False
    low = url.lower()
    if "realtime" in fmt or "-rt" in fmt or low.endswith(".bin") or low.endswith(".json"):
        return False
    if not low.endswith(".zip"):
        return False
    # Accept explicit gtfs format, else any .zip under a GTFS-tagged package.
    return "gtfs" in fmt or fmt in ("", "zip")


def license_of(pkg):
    return pkg.get("license_title") or pkg.get("license_id") or None


def make_record(rec_id, provider, name, subdiv, city, producer_url, license_):
    return {
        "id": rec_id,
        "provider": provider,
        "name": name,
        "cc": CC,
        "subdiv": subdiv,
        "city": city,
        "producer_url": producer_url,
        "hosted_url": None,
        "license": license_,
        "bbox": None,
        "status": "active",
        "official": True,
    }


def collect_from_ckan():
    """Yield candidate records mined from the CKAN catalogue (direct zips)."""
    out = []
    data = http_get_json(API_URL)
    if not data or not data.get("success"):
        return out
    results = (data.get("result") or {}).get("results") or []
    for pkg in results:
        if not isinstance(pkg, dict):
            continue
        provider = ((pkg.get("organization") or {}).get("title")
                    or pkg.get("author")
                    or pkg.get("title")
                    or "Unknown")
        title = pkg.get("title") or pkg.get("name") or provider
        lic = license_of(pkg)
        for res in pkg.get("resources") or []:
            if not isinstance(res, dict) or not is_static_gtfs_zip(res):
                continue
            url = res["url"].strip()
            slug = slugify(pkg.get("name") or title or provider)
            out.append(
                make_record(
                    CC.lower() + "-" + slug,
                    provider,
                    title,
                    None,
                    None,
                    url,
                    lic,
                )
            )
    return out


def main():
    existing = load_existing()
    seen = {r.get("producer_url", "").rstrip("/")
            for r in existing if isinstance(r, dict)}

    candidates = []

    # 6 hardcoded feeds (4 core whole-country networks + 2 niche fallbacks).
    for c in CORE:
        candidates.append(
            make_record(
                CC.lower() + "-" + c["slug"],
                c["provider"],
                c["name"],
                c["subdiv"],
                c["city"],
                c["url"],
                c["license"],
            )
        )

    # Everything else the CKAN catalogue exposes as a direct static GTFS zip
    # (Eurostar, DeWaterbus, TEC again — dedup by producer_url handles overlap).
    candidates.extend(collect_from_ckan())

    added = 0
    for rec in candidates:
        key = rec["producer_url"].rstrip("/")
        if not key or key in seen:
            continue
        existing.append(rec)
        seen.add(key)
        added += 1

    with open(SRC, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    print("+{n} new {cc} feeds".format(n=added, cc=CC))


if __name__ == "__main__":
    main()
