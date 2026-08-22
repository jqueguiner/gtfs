#!/usr/bin/env python3
"""Scraper for Slovakia (SK) open-transit GTFS feeds.

Aggregator: NKOD — Narodny katalog otvorenych dat (data.slovensko.sk, formerly
            data.gov.sk). Slovakia's DCAT-AP-SK national open-data catalog and the
            de-facto transit access point until the Ministry of Transport's formal
            EU NAP ("Elektronicky narodny register informacii dopravy", mindop.sk)
            comes online (an RRP milestone due ~2026).

NKOD is a JS SPA — its CKAN/REST endpoints (/api/3/action/package_search) return
an empty HTML shell, so we MUST use the SPARQL endpoint instead:

  GET https://data.slovensko.sk/api/sparql?query=<url-encoded>
      Accept: application/sparql-results+json

Query (returns dataset title + dcat:downloadURL distribution links):

  PREFIX dcat:<http://www.w3.org/ns/dcat#>
  PREFIX dct:<http://purl.org/dc/terms/>
  SELECT DISTINCT ?title ?dl WHERE {
    ?d a dcat:Dataset; dct:title ?title; dcat:distribution ?dist.
    ?dist dcat:downloadURL ?dl.
    FILTER(CONTAINS(LCASE(STR(?title)),"gtfs"))
  }

The GTFS link is in results.bindings[].dl.value ; title in .title.value. This
reliably yields the ZSR national rail GTFS (www.zsr.sk/.../gtfs/gtfs.zip). Note
the catalog also lists data.slovensko.sk/download?id=... distribution mirrors
that resolve to text/csv (companion stop lists), NOT the GTFS zip — we keep only
distributions whose URL is a real .zip.

Step 2: city GTFS are NOT all mirrored into NKOD. They live on per-city ArcGIS
Hubs. We hardcode the two VERIFIED ArcGIS-Hub item /data endpoints:
  * Bratislava DPB : item aba12fd2cbac4843bc7406151bc66106 -> GTFS_latest.zip
                     (HTTP 200, application/zip, ~4.96 MB, CC-BY-4.0)
  * Kosice DPMK    : item ba941d7bc56a462684a261d4f35ce17d -> CIS.ZIP
                     (HTTP 200, application/zip, ~0.72 MB; CIS/JDF timetable export)

NOT added (no stable GTFS zip): IDS BK regional buses (Google Drive folder, no
single-zip URL); Presov PSK (JSON timetable API, not GTFS); Zilina / Banska
Bystrica / Senica (HTML timetables or GeoJSON only).

stdlib only (json, os, re, urllib). Appends records to data/feeds_full.json (a
JSON array). Dedups against existing records by producer_url (rstrip('/')).
"""
import json
import os
import re
import urllib.parse
import urllib.request

CC = "SK"

SPARQL_URL = "https://data.slovensko.sk/api/sparql"
SPARQL_QUERY = (
    'PREFIX dcat:<http://www.w3.org/ns/dcat#> '
    'PREFIX dct:<http://purl.org/dc/terms/> '
    'SELECT DISTINCT ?title ?dl WHERE { '
    '?d a dcat:Dataset; dct:title ?title; dcat:distribution ?dist. '
    '?dist dcat:downloadURL ?dl. '
    'FILTER(CONTAINS(LCASE(STR(?title)),"gtfs")) }'
)

ARCGIS_ITEM_DATA = "https://www.arcgis.com/sharing/rest/content/items/{item}/data"

SRC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "feeds_full.json"
)

UA = "gtfs-catalog-scraper/1.0 (+adresses)"

# --- Known-operator classification for feeds discovered via SPARQL -----------
# Matched on the direct download host/path so we attach the right operator
# metadata (the NKOD title is a generic Slovak dataset label).
ZSR_RAIL = {
    "provider": (
        "Zeleznice Slovenskej republiky (ZSR) / ZSSK — national passenger rail "
        "(all carriers: ZSSK, RegioJet, Leo Express)"
    ),
    "name": "Grafikon vlakovej dopravy vo formate GTFS (national rail GTFS)",
    "subdiv": None,
    "city": None,
    "license": None,
}

# --- Hardcoded verified ArcGIS-Hub city feeds (not fully mirrored into NKOD) --
ARCGIS_FEEDS = [
    {
        "item": "aba12fd2cbac4843bc7406151bc66106",
        "provider": "Dopravny podnik Bratislava, a.s. (DPB) — city MHD (tram/trolley/bus)",
        "name": "DPB Bratislava MHD GTFS (GTFS_latest.zip)",
        "subdiv": "Bratislavsky kraj",
        "city": "Bratislava",
        "license": "CC-BY-4.0",
    },
    {
        "item": "ba941d7bc56a462684a261d4f35ce17d",
        "provider": "Dopravny podnik mesta Kosice, a.s. (DPMK) — tram/trolley/bus MHD",
        "name": "DPMK Kosice — Cestovny poriadok MHD (CIS export)",
        "subdiv": "Kosicky kraj",
        "city": "Kosice",
        "license": None,
    },
]


def slugify(s):
    s = s.lower()
    trans = {
        "a": "a", "c": "c", "d": "d", "e": "e", "i": "i", "l": "l",
        "n": "n", "o": "o", "r": "r", "s": "s", "t": "t", "u": "u",
        "y": "y", "z": "z",
        "á": "a", "ä": "a", "č": "c", "ď": "d",
        "é": "e", "í": "i", "ĺ": "l", "ľ": "l",
        "ň": "n", "ó": "o", "ô": "o", "ŕ": "r",
        "š": "s", "ť": "t", "ú": "u", "ý": "y",
        "ž": "z",
    }
    s = "".join(trans.get(ch, ch) for ch in s)
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


def fetch_sparql():
    """Enumerate GTFS distributions from NKOD via SPARQL.

    Returns a list of (title, download_url) tuples. Empty on any failure.
    """
    query = urllib.parse.quote(SPARQL_QUERY)
    url = "{}?query={}".format(SPARQL_URL, query)
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/sparql-results+json",
            "User-Agent": UA,
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode("utf-8", "replace")
    data = json.loads(raw)
    out = []
    bindings = (((data or {}).get("results") or {}).get("bindings")) or []
    for b in bindings:
        if not isinstance(b, dict):
            continue
        title = ((b.get("title") or {}).get("value") or "").strip()
        dl = ((b.get("dl") or {}).get("value") or "").strip()
        if dl:
            out.append((title, dl))
    return out


def is_gtfs_zip(url):
    """Keep only distributions that are a real GTFS .zip download.

    NKOD also exposes data.slovensko.sk/download?id=... mirrors that resolve to
    text/csv companion files, not the GTFS zip — filter those out.
    """
    return bool(re.search(r"\.zip($|\?)", url, re.IGNORECASE))


def classify(url, title):
    """Return operator metadata dict for a SPARQL-discovered GTFS zip."""
    low = url.lower()
    if "zsr.sk" in low and "gtfs" in low:
        return dict(ZSR_RAIL)
    # Generic fallback: a GTFS zip in NKOD we don't specifically know.
    return {
        "provider": title or "NKOD GTFS provider",
        "name": title or "SK GTFS feed (NKOD)",
        "subdiv": None,
        "city": None,
        "license": None,
    }


def make_record(producer_url, meta):
    slug_src = meta.get("city") or meta.get("provider") or producer_url
    slug = slugify(slug_src)
    if not slug:
        slug = slugify(producer_url)
    return {
        "id": "{}-{}".format(CC.lower(), slug),
        "provider": meta["provider"],
        "name": meta["name"],
        "cc": CC,
        "subdiv": meta.get("subdiv"),
        "city": meta.get("city"),
        "producer_url": producer_url,
        "hosted_url": None,
        "license": meta.get("license"),
        "bbox": None,
        "status": "active",
        "official": True,
    }


def build_candidates():
    candidates = []

    # (1) NKOD SPARQL enumeration
    try:
        pairs = fetch_sparql()
    except Exception as e:  # network / parse failures must not abort the run
        print("WARN: NKOD SPARQL fetch failed: {}".format(e))
        pairs = []
    seen_urls = set()
    for title, dl in pairs:
        if not is_gtfs_zip(dl):
            continue
        key = dl.rstrip("/")
        if key in seen_urls:
            continue
        seen_urls.add(key)
        candidates.append(make_record(dl, classify(dl, title)))

    # (2) Hardcoded verified ArcGIS-Hub city feeds
    for feed in ARCGIS_FEEDS:
        producer_url = ARCGIS_ITEM_DATA.format(item=feed["item"])
        candidates.append(make_record(producer_url, feed))

    return candidates


def main():
    existing = load_existing()
    seen = set()
    for r in existing:
        pu = r.get("producer_url")
        if pu:
            seen.add(pu.rstrip("/"))

    added = 0
    for rec in build_candidates():
        key = rec["producer_url"].rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        existing.append(rec)
        added += 1

    os.makedirs(os.path.dirname(SRC), exist_ok=True)
    with open(SRC, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    print("+{} new {} feeds".format(added, CC))


if __name__ == "__main__":
    main()