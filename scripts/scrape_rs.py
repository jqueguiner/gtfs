#!/usr/bin/env python3
"""
Scraper: Serbia (RS) — data.gov.rs (Serbian national open-data portal).

Serbia is NOT an EU member, so there is no legally-mandated NeTEx National Access
Point. data.gov.rs is the de-facto national aggregator and enumerates ALL known
open GTFS feeds. It runs the French 'udata' platform (same engine as
data.gouv.fr), so the API mirrors that schema:

    GET https://data.gov.rs/api/1/datasets/?q=<query>&page_size=50
    -> {"total": N, "page": 1, "page_size": 50, "next_page": null,
        "previous_page": null, "data": [ <dataset>, ... ]}

Each <dataset> has: "slug", "title", "license", and a "resources" array. Each
resource has (among others): "url", "format", "title". The GTFS download is the
resource whose format == "zip" (or whose url ends with .zip); its "url" is a
stable https://data.gov.rs/s/resources/<slug>/<timestamp>/<file>.zip path
(verified HTTP 200 application/zip).

We query q=gtfs AND q=prevoz ('prevoz' = transport) and merge, deduping datasets
by slug, so a future rename that drops the literal 'gtfs' token is still caught.
This yields all 6 feeds: Belgrade urban, Belgrade suburban, Nis, Kragujevac,
Subotica, Uzice (vs ~1 currently in the Mobility Database).

No auth / API key required; CORS-open. stdlib only. Appends records to
data/feeds_full.json (a JSON array), dedup by producer_url.
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

CC = "RS"
TIMEOUT = 30
API = "https://data.gov.rs/api/1/datasets/?q={q}&page_size=50"
QUERIES = ["gtfs", "prevoz"]
# udata license id -> human string. "sodl" is the Serbian Open Data Licence.
LICENSE_MAP = {
    "sodl": "Serbian Open Data Licence (sodl)",
    "notspecified": None,
    "": None,
    None: None,
}
HEADERS = {
    "Accept": "application/json",
    "User-Agent": "adresses-gtfs-catalog/1.0 (+https://github.com/jqueguiner/gtfs)",
}

# Known dataset slug -> (subdiv, city) enrichment. Titles are Serbian Cyrillic on
# the portal; we attach clean Latin city/subdiv metadata. Any dataset NOT in this
# map is still ingested (city/subdiv fall back to None), so new feeds are picked
# up automatically.
SLUG_META = {
    "gradski-javni-prevoz-u-beogradu-gtfs":        ("Grad Beograd", "Belgrade"),
    "prigradski-javni-prevoz-u-u-beogradu-gtfs":   ("Grad Beograd", "Belgrade"),
    "javni-prevoz-i-gtfs":                         ("Nisavski okrug", "Nis"),
    "gtfs-kragujevats":                            ("Sumadijski okrug", "Kragujevac"),
    "gtfs-subotitsa":                              ("Severnobacki okrug", "Subotica"),
    "gtfs-uzhitse":                                ("Zlatiborski okrug", "Uzice"),
}


def load_existing():
    try:
        with open(SRC, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except (FileNotFoundError, ValueError):
        pass
    return []


def fetch_json(url):
    """GET url and parse JSON. Returns dict on success, None on any failure."""
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read()
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


def iter_datasets(payload):
    """Yield dataset dicts from a udata list payload (handles pagination defensively)."""
    if not isinstance(payload, dict):
        return
    data = payload.get("data")
    if isinstance(data, list):
        for ds in data:
            if isinstance(ds, dict):
                yield ds


def pick_zip_resource(dataset):
    """Return the (url, title) of the GTFS zip resource, or (None, None).

    A resource qualifies if its format is 'zip' OR its url ends with '.zip'.
    Prefer a format=='zip' + gtfs-looking name; fall back to any .zip url."""
    resources = dataset.get("resources")
    if not isinstance(resources, list):
        return None, None
    best = None
    for r in resources:
        if not isinstance(r, dict):
            continue
        url = r.get("url")
        if not isinstance(url, str) or not url:
            continue
        fmt = (r.get("format") or "").strip().lower()
        is_zip = fmt == "zip" or url.lower().rstrip("/").endswith(".zip")
        if not is_zip:
            continue
        title = r.get("title") or ""
        # Rank: explicit zip format beats a mere .zip url; a gtfs-ish name wins.
        score = 0
        if fmt == "zip":
            score += 2
        if "gtfs" in (title.lower() + url.lower()):
            score += 1
        if best is None or score > best[0]:
            best = (score, url, title)
    if best is None:
        return None, None
    return best[1], best[2]


def make_record(rec_id, provider, name, subdiv, city, producer_url, license_str):
    return {
        "id": rec_id,
        "provider": provider,
        "name": name,
        "cc": CC,
        "subdiv": subdiv,
        "city": city,
        "producer_url": producer_url,
        "hosted_url": None,
        "license": license_str,
        "bbox": None,
        "status": "active",
        "official": True,
    }


def main():
    existing = load_existing()
    seen_urls = {
        r.get("producer_url", "").rstrip("/")
        for r in existing
        if isinstance(r, dict) and r.get("producer_url")
    }

    # Collect datasets across all queries, deduped by slug.
    datasets_by_slug = {}
    for q in QUERIES:
        payload = fetch_json(API.format(q=q))
        for ds in iter_datasets(payload):
            slug = ds.get("slug")
            if not slug:
                continue
            # First query to surface a slug wins; keep it stable.
            datasets_by_slug.setdefault(slug, ds)

    added = 0
    for slug, ds in datasets_by_slug.items():
        producer_url, res_title = pick_zip_resource(ds)
        if not producer_url:
            continue  # no GTFS zip in this dataset — skip
        key = producer_url.rstrip("/")
        if key in seen_urls:
            continue

        title = ds.get("title") or res_title or slug
        subdiv, city = SLUG_META.get(slug, (None, None))
        # Provider: prefer the dataset organization name, else the city, else title.
        org = ds.get("organization")
        provider = None
        if isinstance(org, dict):
            provider = org.get("name")
        if not provider:
            provider = city or title
        lic_raw = ds.get("license")
        license_str = LICENSE_MAP.get(lic_raw, lic_raw)

        rec = make_record(
            CC.lower() + "-" + slug,
            provider,
            title,
            subdiv,
            city,
            producer_url,
            license_str,
        )
        existing.append(rec)
        seen_urls.add(key)
        added += 1

    with open(SRC, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    print("+{n} new {cc} feeds".format(n=added, cc=CC))


if __name__ == "__main__":
    main()
