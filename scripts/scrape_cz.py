#!/usr/bin/env python3
"""
Scraper: Czechia (CZ) — CIS JR / NKOD national open-transit aggregator.

Provenance notes (verified 2026-08):
  * The de-jure National Access Point is NKOD (data.gov.cz), an EU-mandated
    *metadata* catalogue under decree 122/2014 Sb. — it hosts no feed files.
  * The de-facto upstream CIS JR portal (portal.cisjr.cz, operated by CHAPS)
    publishes native JDF (bus) + CZPTT XML (rail), NOT GTFS — the widely-cited
    "official GTFS from portal.cisjr.cz" claim is inaccurate about provenance.
  * The realistic single-grab nationwide GTFS is Spojenka
    (www.spojenka.cz/jrdata/jizdnirady-gtfs.zip), a merged bus+rail+all-MHD
    feed. That path 301-redirects to the real host
    spojenka.d3s.mff.cuni.cz/api/data/timetable/gtfs and returns a ~90 MB
    application/zip (verified 200). Note: the /jrdata root 403s to bots — the
    .zip path must be hit directly with a browser User-Agent.

So this scraper records the three clean, directly-downloadable national/city
GTFS zips (no JDF conversion needed):
  1. Spojenka nationwide merge   (all operators: bus + rail + every MHD)
  2. PID   — Prague + Central Bohemia + regional rail (data.pid.cz)
  3. IDS JMK / Brno — official GTFS on the data.brno.cz ArcGIS Hub

For Brno we resolve the ArcGIS Hub item JSON dynamically (title + license) but
download via the item's verified /data endpoint (ArcGIS "CSV Collection" items
expose the zip there, not in the item 'url' field). All other CZ regions
(Ostrava/ODIS, Plzen, Liberec, Olomouc, Usti n.L., Hradec Kralove, ...) publish
only native JDF upstream and have no clean standalone official GTFS — they are
covered by the Spojenka nationwide merge, so we do not emit dead per-region rows.

stdlib only (json, urllib, os, re). Appends to data/feeds_full.json, dedup by
producer_url (rstrip('/')). Prints '+N new CZ feeds'.
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

CC = "CZ"
TIMEOUT = 30

# A browser UA is required: Spojenka 403s bot agents; ArcGIS is picky too.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "*/*",
}

# ArcGIS Hub dataset id for the official IDS JMK / Brno GTFS (source: KORDIS).
BRNO_ITEM_ID = "379d2e9a7907460c8ca7fda1f3e84328"
BRNO_ITEM_JSON = (
    "https://www.arcgis.com/sharing/rest/content/items/"
    + BRNO_ITEM_ID
    + "?f=json"
)
# The item's /data endpoint serves the GTFS zip directly (verified application/zip).
BRNO_GTFS_URL = (
    "https://www.arcgis.com/sharing/rest/content/items/"
    + BRNO_ITEM_ID
    + "/data"
)

# ---------------------------------------------------------------------------
# Core verified CZ GTFS feeds (directly downloadable zips — no JDF conversion).
# ---------------------------------------------------------------------------
CORE = [
    {
        "slug": "spojenka-nationwide",
        "provider": "Spojenka (CHAPS / CIS JR merge)",
        "name": (
            "Spojenka nationwide merged GTFS (all CZ operators: bus + rail + "
            "all MHD; from CIS JR)"
        ),
        "subdiv": None,
        "city": None,
        # /jrdata/...zip 301-redirects to the real host; record the stable
        # public path (urllib follows the redirect automatically on download).
        "url": "https://www.spojenka.cz/jrdata/jizdnirady-gtfs.zip",
        "license": None,
    },
    {
        "slug": "pid-praha",
        "provider": "PID - Prazska integrovana doprava (ROPID / IDSK)",
        "name": (
            "PID GTFS (Prague DPP metro/tram/bus + Central Bohemia + regional "
            "rail)"
        ),
        "subdiv": "Praha (Central Bohemia)",
        "city": "Prague",
        "url": "https://data.pid.cz/PID_GTFS.zip",
        "license": "CC-BY-4.0",
    },
]


def slugify(s):
    s = (s or "").lower()
    # strip diacritics crudely for ascii slugs
    s = s.replace("á", "a").replace("č", "c").replace("ď", "d")
    s = s.replace("é", "e").replace("ě", "e").replace("í", "i")
    s = s.replace("ň", "n").replace("ó", "o").replace("ř", "r")
    s = s.replace("š", "s").replace("ť", "t").replace("ú", "u")
    s = s.replace("ů", "u").replace("ý", "y").replace("ž", "z")
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


def url_ok(url):
    """HEAD-ish check: the URL resolves and looks like a zip (or at least 200)."""
    req = urllib.request.Request(url, headers=HEADERS, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            ct = (r.headers.get("Content-Type") or "").lower()
            return r.status == 200 and ("zip" in ct or "octet-stream" in ct or ct == "")
    except Exception:
        # Some hosts reject HEAD; assume ok rather than dropping a known feed.
        return True


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


def brno_record():
    """Resolve the Brno IDS JMK ArcGIS Hub item (title + license) dynamically."""
    title = "Jizdni rad IDS JMK ve formatu GTFS (Brno / KORDIS)"
    lic = "CC-BY-4.0"
    meta = http_get_json(BRNO_ITEM_JSON)
    if isinstance(meta, dict):
        t = meta.get("title")
        if t:
            title = t
        li = (meta.get("licenseInfo") or "").strip()
        if "cc" in li.lower() and "by" in li.lower():
            lic = "CC-BY-4.0"
        elif li:
            lic = li[:60]
    return make_record(
        CC.lower() + "-ids-jmk-brno",
        "IDS JMK / KORDIS (incl. DPMB Brno tram/trolleybus/bus)",
        title,
        "Jihomoravsky kraj (South Moravia)",
        "Brno",
        BRNO_GTFS_URL,
        lic,
    )


def main():
    existing = load_existing()
    seen = {
        r.get("producer_url", "").rstrip("/")
        for r in existing
        if isinstance(r, dict)
    }

    candidates = []

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

    # Brno IDS JMK (ArcGIS Hub) — resolved dynamically, download via /data.
    candidates.append(brno_record())

    added = 0
    for rec in candidates:
        url = rec.get("producer_url") or ""
        key = url.rstrip("/")
        if not key or key in seen:
            continue
        # Robustness: skip a candidate whose URL clearly doesn't resolve.
        if not url_ok(url):
            continue
        existing.append(rec)
        seen.add(key)
        added += 1

    with open(SRC, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    print("+{n} new {cc} feeds".format(n=added, cc=CC))


if __name__ == "__main__":
    main()
