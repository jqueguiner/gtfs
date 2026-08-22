#!/usr/bin/env python3
"""
Scraper: Finland (FI) — FINAP, the Finnish National Access Point.

FINAP (finap.fi) is Finland's legally-mandated EU National Access Point, operated by
Fintraffic Oy for Traficom. Its service-search API is UNAUTHENTICATED and enumerates
~1000 registered transport services, each with an `external-interface-links` array of
data interfaces. This is the single best programmatic enumeration of every Finnish
operator's GTFS feed.

  GET https://finap.fi/ote/service-search?response_format=json   (no auth)
      -> {"results": [ <service>, ... ]}

Each <service> has:
  - "operator-name" / "name"           (operator + service title)
  - "sub-type"                         ("schedule", "terminal", ...)
  - "external-interface-links": [ <link>, ... ]

Each <link> has:
  - "external-interface": {"url": "<gtfs zip url>", "description": [...]}   (URL lives HERE, nested)
  - "format":       ["GTFS"], ["NeTEx"], ...        (we keep links whose format contains "GTFS")
  - "data-content": ["route-and-schedule"], ...      (we require "route-and-schedule")
  - "license":      "CC BY 4.0" | "<url>" | ""       (optional, free-text)
  - "gtfs-import-error": "<msg>"                      (present => FINAP could not import the zip; skip)

We keep only GTFS + route-and-schedule links that carry a URL and have NO
`gtfs-import-error`, dedup by URL, and emit one catalog record per feed.

Supplemented with feeds that are national/aggregated and not always exposed as clean
per-operator GTFS in the service-search:
  - VR passenger rail  (rata.digitraffic.fi Digitraffic GTFS)
  - Vallu / ELY-centre regional bus (koontikartta.navici.com gtfs_vallu.zip)
  - Finavia domestic flights        (koontikartta.navici.com gtfs_finavia.zip)

stdlib only (json, urllib, os, re). Appends to data/feeds_full.json (a JSON array),
dedup by producer_url (rstrip('/')). Prints '+N new FI feeds'.
"""

import json
import os
import re
import urllib.request
import urllib.error
from urllib.parse import urlparse

SRC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "feeds_full.json",
)

CC = "FI"
API_URL = "https://finap.fi/ote/service-search?response_format=json"
TIMEOUT = 90
HEADERS = {
    "User-Agent": "adresses-gtfs-catalog/1.0 (+https://github.com/jqueguiner/gtfs)",
    "Accept": "application/json",
}

# Known host -> representative (subdiv, city), to enrich a handful of major operators.
# (Best-effort labelling only; unknown hosts fall back to null subdiv/city.)
HOST_HINTS = {
    "infopalvelut.storage.hsldev.com": ("Uusimaa", "Helsinki"),
    "ekstrat.tampere.fi": ("Pirkanmaa", "Tampere"),
    "data.foli.fi": ("Varsinais-Suomi", "Turku"),
}

# Supplemental national / aggregated feeds not reliably exposed as per-operator GTFS.
SUPPLEMENTAL = [
    {
        "slug": "vr-rail",
        "provider": "VR-Yhtyma Oyj",
        "name": "VR passenger rail (Digitraffic GTFS, national)",
        "url": "https://rata.digitraffic.fi/api/v1/trains/gtfs-all.zip",
        "subdiv": None,
        "city": None,
        "license": "CC BY 4.0",
    },
    {
        "slug": "vallu-ely",
        "provider": "Traficom / ELY-keskukset (Vallu)",
        "name": "Vallu ELY-centre regional bus (national dump)",
        "url": "https://koontikartta.navici.com/tiedostot/gtfs_vallu.zip",
        "subdiv": None,
        "city": None,
        "license": "CC BY 4.0",
    },
    {
        "slug": "finavia-flights",
        "provider": "Finavia Oyj",
        "name": "Finavia domestic flights (GTFS)",
        "url": "https://koontikartta.navici.com/tiedostot/gtfs_finavia.zip",
        "subdiv": None,
        "city": None,
        "license": "CC BY 4.0",
    },
]


def slugify(s):
    s = (s or "").lower()
    s = s.encode("ascii", "ignore").decode("ascii")
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


def clean_license(lic):
    if lic is None:
        return None
    lic = str(lic).strip()
    return lic or None


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


def fetch_services():
    """Fetch the FINAP service-search JSON. Returns [] on any failure."""
    req = urllib.request.Request(API_URL, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, ValueError, OSError) as e:
        print("WARN: could not fetch FINAP service-search: {}".format(e))
        return []
    results = data.get("results") if isinstance(data, dict) else None
    return results if isinstance(results, list) else []


def link_url(link):
    """The GTFS zip URL is nested under external-interface.url; tolerate a flat url too."""
    if not isinstance(link, dict):
        return None
    ei = link.get("external-interface")
    url = None
    if isinstance(ei, dict) and ei.get("url"):
        url = ei["url"]
    else:
        url = link.get("url")
    return url.strip() if isinstance(url, str) else url


def iter_feed_candidates(services):
    """Yield (provider, name, subdiv, city, url, license) for each usable GTFS feed."""
    for s in services:
        if not isinstance(s, dict):
            continue
        provider = s.get("operator-name") or s.get("name") or "Unknown operator"
        svc_name = s.get("name") or provider
        for link in s.get("external-interface-links") or []:
            if not isinstance(link, dict):
                continue
            fmts = [str(x).upper() for x in (link.get("format") or [])]
            if "GTFS" not in fmts:
                continue
            dcs = [str(x) for x in (link.get("data-content") or [])]
            if not any("route-and-schedule" in d for d in dcs):
                continue
            # FINAP itself flagged the zip as unimportable/broken -> skip.
            if link.get("gtfs-import-error"):
                continue
            url = link_url(link)
            if not url or not str(url).lower().startswith("http"):
                continue
            subdiv, city = HOST_HINTS.get(urlparse(url).netloc, (None, None))
            yield (
                provider,
                "GTFS - {} (FINAP)".format(svc_name),
                subdiv,
                city,
                url,
                clean_license(link.get("license")),
            )


def main():
    existing = load_existing()
    seen = {r.get("producer_url", "").rstrip("/") for r in existing if isinstance(r, dict)}
    used_ids = {r.get("id") for r in existing if isinstance(r, dict)}

    candidates = []

    # (1) FINAP-enumerated per-operator GTFS feeds.
    for provider, name, subdiv, city, url, lic in iter_feed_candidates(fetch_services()):
        p = urlparse(url)
        # Full host+path slug keeps per-operator feeds distinct and stable
        # (e.g. .../gtfs/069/gtfs.zip vs .../gtfs/067/gtfs.zip).
        base = slugify(p.netloc + "-" + p.path) or slugify(provider)
        candidates.append((CC.lower() + "-" + base, provider, name, subdiv, city, url, lic))

    # (2) Supplemental national/aggregated feeds.
    for feed in SUPPLEMENTAL:
        candidates.append(
            (
                CC.lower() + "-" + feed["slug"],
                feed["provider"],
                feed["name"],
                feed["subdiv"],
                feed["city"],
                feed["url"],
                feed["license"],
            )
        )

    added = 0
    for rec_id, provider, name, subdiv, city, url, lic in candidates:
        key = url.rstrip("/")
        if key in seen:
            continue
        # Ensure a unique id even if two feeds slugify identically.
        uid = rec_id
        n = 2
        while uid in used_ids:
            uid = "{}-{}".format(rec_id, n)
            n += 1
        rec = make_record(uid, provider, name, subdiv, city, url, lic)
        existing.append(rec)
        seen.add(key)
        used_ids.add(uid)
        added += 1

    with open(SRC, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    print("+{n} new {cc} feeds".format(n=added, cc=CC))


if __name__ == "__main__":
    main()
