#!/usr/bin/env python3
"""
Scraper: Cyprus (CY) — Cyprus National Access Point (traffic4cyprus.org.cy).

CyNAP is Cyprus's EU-mandated National Access Point, run by the Public Works
Department / Ministry of Transport. It is a standard CKAN portal. The
`publictransportstatic` package enumerates all 7 GTFS operator feeds; the files
themselves are self-hosted on motionbuscard.org.cy.

  GET https://traffic4cyprus.org.cy/api/3/action/package_show?id=publictransportstatic
      -> {"success": true, "result": {"resources": [ <resource>, ... ], ...}}

Each <resource> in result.resources[] has:
  - "name"   : operator + city, e.g. "EMEL (Limassol)"
  - "format" : "GTFS" for the static zips
  - "url"    : direct motionbuscard.org.cy downloadfile zip URL. The path
               contains a literal backslash which CKAN returns URL-encoded as
               %5C, e.g.
               https://motionbuscard.org.cy/opendata/downloadfile?file=GTFS%5C6_google_transit.zip&rel=True
  - "license"/... : per-resource license (portal-level license_id is CC-BY-4.0)

We keep only resources whose format is GTFS and whose url points at the
motionbuscard downloadfile endpoint, dedup by producer_url, map the operator to
its city/district, and emit one catalog record per feed.

Data covers the Republic of Cyprus (south) only; northern Cyprus is not
included. Coverage is national across 7 operators (5 urban + intercity +
park-and-ride).

stdlib only (json, urllib, os, re). Appends to data/feeds_full.json (a JSON
array), dedup by producer_url (rstrip('/')). Prints '+N new CY feeds'.
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

CC = "CY"
API_BASE = "https://traffic4cyprus.org.cy/api/3/action/package_show?id="
STATIC_DATASET = "publictransportstatic"
TIMEOUT = 90
HEADERS = {
    "User-Agent": "adresses-gtfs-catalog/1.0 (+https://github.com/jqueguiner/gtfs)",
    "Accept": "application/json",
}
PORTAL_LICENSE = "CC-BY-4.0"

# Operator id (from the GTFS\<id>_google_transit.zip path) -> (subdiv, city).
# Cyprus districts are the natural subdivisions; intercity/park-and-ride are
# nationwide (no single city).
OPERATOR_HINTS = {
    "2": ("Paphos", "Paphos"),          # OSYPA
    "4": ("Famagusta", "Ayia Napa"),    # OSEA (free area of Famagusta district)
    "5": (None, None),                  # Intercity buses (nationwide)
    "6": ("Limassol", "Limassol"),      # EMEL
    "9": ("Nicosia", "Nicosia"),        # NPT
    "10": ("Larnaca", "Larnaca"),       # LPT
    "11": (None, None),                 # Pame Express (park & ride, nationwide)
}

# Fallback operator list, used only if the CKAN API is unreachable so the
# scraper still populates the known 7 feeds. Mirrors the aggregator's resources.
FALLBACK_RESOURCES = [
    {"name": "EMEL (Limassol)",
     "url": "https://motionbuscard.org.cy/opendata/downloadfile?file=GTFS%5C6_google_transit.zip&rel=True"},
    {"name": "OSYPA (Pafos)",
     "url": "https://motionbuscard.org.cy/opendata/downloadfile?file=GTFS%5C2_google_transit.zip&rel=True"},
    {"name": "OSEA (Famagusta)",
     "url": "https://motionbuscard.org.cy/opendata/downloadfile?file=GTFS%5C4_google_transit.zip&rel=True"},
    {"name": "Intercity buses",
     "url": "https://motionbuscard.org.cy/opendata/downloadfile?file=GTFS%5C5_google_transit.zip&rel=True"},
    {"name": "NPT (Nicosia)",
     "url": "https://motionbuscard.org.cy/opendata/downloadfile?file=GTFS%5C9_google_transit.zip&rel=True"},
    {"name": "LPT (Larnaca)",
     "url": "https://motionbuscard.org.cy/opendata/downloadfile?file=GTFS%5C10_google_transit.zip&rel=True"},
    {"name": "Pame Express (Park and Ride)",
     "url": "https://motionbuscard.org.cy/opendata/downloadfile?file=GTFS%5C11_google_transit.zip&rel=True"},
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
    if not lic:
        return None
    # Per-resource strings like "Licence provided" carry no real license id;
    # fall back to the portal-level CC-BY-4.0 for those.
    if lic.lower() in ("licence provided", "license provided"):
        return PORTAL_LICENSE
    return lic


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


def fetch_resources(dataset_id):
    """Fetch result.resources[] from a CKAN package_show call. [] on failure."""
    url = API_BASE + dataset_id
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, ValueError, OSError) as e:
        print("WARN: could not fetch CKAN {}: {}".format(dataset_id, e))
        return []
    if not isinstance(data, dict) or not data.get("success"):
        return []
    result = data.get("result")
    if not isinstance(result, dict):
        return []
    resources = result.get("resources")
    return resources if isinstance(resources, list) else []


def operator_id_from_url(url):
    """Extract N from .../file=GTFS\\N_google_transit.zip (backslash may be %5C)."""
    m = re.search(r"GTFS(?:%5[Cc]|\\|/)?(\d+)_google_transit\.zip", url)
    return m.group(1) if m else None


def is_gtfs_static(res):
    """True for the static GTFS zip resources on motionbuscard."""
    if not isinstance(res, dict):
        return False
    fmt = str(res.get("format") or "").strip().upper()
    url = str(res.get("url") or "")
    if "GTFS" not in fmt and "GTFS" not in url:
        return False
    if "motionbuscard.org.cy" not in url:
        return False
    if "downloadfile" not in url:
        return False
    return url.lower().startswith("http")


def iter_feed_candidates(resources):
    """Yield (provider, name, subdiv, city, url, license) per usable GTFS feed."""
    for res in resources:
        if not is_gtfs_static(res):
            continue
        url = str(res["url"]).strip()
        name = (res.get("name") or "").strip() or "Cyprus operator"
        # provider is the operator name without the parenthetical city.
        provider = re.sub(r"\s*\(.*?\)\s*$", "", name).strip() or name
        op_id = operator_id_from_url(url)
        subdiv, city = OPERATOR_HINTS.get(op_id, (None, None))
        feed_name = "GTFS — {} (CyNAP)".format(name)
        yield (provider, feed_name, subdiv, city, url, clean_license(res.get("license")))


def main():
    existing = load_existing()
    seen = {r.get("producer_url", "").rstrip("/") for r in existing if isinstance(r, dict)}
    used_ids = {r.get("id") for r in existing if isinstance(r, dict)}

    resources = fetch_resources(STATIC_DATASET)
    if not resources:
        print("WARN: CKAN returned no resources; using fallback operator list")
        resources = FALLBACK_RESOURCES

    candidates = []
    for provider, name, subdiv, city, url, lic in iter_feed_candidates(resources):
        op_id = operator_id_from_url(url)
        # Stable, distinct slug per operator: prefer operator id, else name.
        if op_id:
            base = "{}-{}".format(slugify(provider) or "operator", op_id)
        else:
            base = slugify(provider) or slugify(name) or "feed"
        rec_id = CC.lower() + "-" + base
        candidates.append((rec_id, provider, name, subdiv, city, url, lic))

    added = 0
    for rec_id, provider, name, subdiv, city, url, lic in candidates:
        key = url.rstrip("/")
        if key in seen:
            continue
        uid = rec_id
        n = 2
        while uid in used_ids:
            uid = "{}-{}".format(rec_id, n)
            n += 1
        rec = make_record(uid, provider, name, subdiv, city, url, lic or PORTAL_LICENSE)
        existing.append(rec)
        seen.add(key)
        used_ids.add(uid)
        added += 1

    with open(SRC, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    print("+{n} new {cc} feeds".format(n=added, cc=CC))


if __name__ == "__main__":
    main()
