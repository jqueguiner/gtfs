#!/usr/bin/env python3
"""
Portugal (PT) GTFS feed scraper.

Sources
-------
1. dados.gov.pt (uData / national open-data portal) -- practical GTFS aggregator.
   GET https://dados.gov.pt/api/1/datasets/?q=<term>&page_size=50  (JSON)
   Each dataset has resources[]; GTFS resources have format 'zip'/'gtfs' and a
   direct 'url' field pointing at the .zip (dados.gov.pt/s/resources/... or an
   external operator host: github raw, tub.pt, cm-agueda CKAN, ...).
   We iterate q=GTFS, q=transportes, q=horarios and paginate via 'next_page'.
   NOTE: many "GTFS"-tagged datasets on dados.gov.pt are actually OGC-API
   collections (geoportal.tmlmobilidade.pt/ogc-api/...) exposing JSON/GeoJSON,
   or NeTEx / shapefile / stops-only ("paragens") zips -- NOT a bulk GTFS feed.
   Those are filtered out (see is_gtfs_zip_resource).

2. Porto CKAN (opendata.porto.digital) -- STCP + Metro do Porto.
   GET https://opendata.porto.digital/api/3/action/package_search?q=GTFS&rows=50
   Per dataset we pick the single latest zip resource (prefer the one whose name
   contains 'Mais Recente', else the newest DD-MM-YYYY-dated .zip download url).

3. Direct operator feeds not reliably (or not as a clean zip) on the portals:
   Carris, Carris Metropolitana, TUB Braga.

The IMT NAP (nap-portugal.imt-ip.pt) serves STePP shapefiles / emerging NeTEx,
not a GTFS list API -- it is intentionally skipped.

Each record appended to data/feeds_full.json has EXACTLY these keys:
  id, provider, name, cc, subdiv, city, producer_url, hosted_url,
  license, bbox, status, official
Dedup is by producer_url (rstrip('/')). Stdlib only.
"""

import json
import os
import re
import urllib.request

CC = "PT"
UA = "Mozilla/5.0 (compatible; gtfs-catalog/1.0; +https://github.com/jqueguiner/gtfs)"
TIMEOUT = 60

SRC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "feeds_full.json",
)

UDATA_TERMS = ["GTFS", "transportes", "horarios"]
UDATA_BASE = "https://dados.gov.pt/api/1/datasets/?q=%s&page_size=50"
PORTO_CKAN = "https://opendata.porto.digital/api/3/action/package_search?q=GTFS&rows=50"

# uData / CKAN license id -> SPDX-ish label
LICENSE_MAP = {
    "cc-by": "CC-BY-4.0",
    "cc-zero": "CC0-1.0",
    "cc-by-sa": "CC-BY-SA-4.0",
    "odc-by": "ODC-BY-1.0",
    "odc-odbl": "ODbL-1.0",
    "notspecified": None,
    "other-open": None,
    "": None,
    None: None,
}

# Direct operator feeds not reliably (or not as a clean zip) on the portals.
DIRECT_FEEDS = [
    {
        "provider": "Carris (Companhia Carris de Ferro de Lisboa)",
        "name": "Carris — Lisbon buses, trams, funiculars (GTFS)",
        "city": "Lisbon",
        "subdiv": "Lisboa",
        "producer_url": "https://gateway.carris.pt/gateway/gtfs/api/v2.11/GTFS",
        "license": None,
    },
    {
        "provider": "Carris Metropolitana",
        "name": "Carris Metropolitana — Lisbon metropolitan area buses (GTFS)",
        "city": "Lisbon",
        "subdiv": "Lisboa",
        "producer_url": "https://github.com/carrismetropolitana/gtfs/raw/live/CarrisMetropolitana.zip",
        "license": None,
    },
    {
        "provider": "TUB — Transportes Urbanos de Braga",
        "name": "TUB — Braga urban transport (GTFS)",
        "city": "Braga",
        "subdiv": "Braga",
        "producer_url": "https://www.tub.pt/developer/gtfs/feed/tub.zip",
        "license": None,
    },
]


def http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def slugify(s):
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "feed"


def is_gtfs_zip_resource(res):
    """True iff this uData/CKAN resource is a direct GTFS zip download.

    Requires a real .zip url with a positive GTFS signal, and rejects the common
    non-GTFS payloads that live under GTFS/transporte datasets on dados.gov.pt:
    OGC-API json/geojson collection endpoints, NeTEx exports, shapefiles, and
    stops-only ("paragens") zips.
    """
    url = (res.get("url") or "").strip()
    if not url:
        return False
    fmt = (res.get("format") or "").lower()
    title = (res.get("title") or res.get("name") or "").lower()
    low = url.lower()
    # Reject OGC-API / json collection endpoints outright.
    if "ogc-api" in low or low.endswith(("?f=json", "?f=jsonld")):
        return False
    if fmt in ("json", "json-ld", "geojson", "schema+json", "html", "url"):
        return False
    # Require a real .zip download.
    if not low.endswith(".zip"):
        return False
    blob = title + " " + low
    # Reject non-GTFS payloads: NeTEx, shapefiles, stops-only ("paragens").
    if re.search(r"netex|shapefile|\bshp\b|redetransportes|/paragens", blob):
        return False
    # Positive GTFS signal: explicit gtfs format, or 'gtfs' in title/url.
    return fmt == "gtfs" or "gtfs" in blob


def scrape_udata():
    """Yield feed records from dados.gov.pt across all query terms + pagination."""
    seen_ds = set()
    for term in UDATA_TERMS:
        url = UDATA_BASE % term
        pages = 0
        while url and pages < 25:
            pages += 1
            try:
                data = http_json(url)
            except Exception as e:
                print("  uData fetch failed (%s): %s" % (term, e))
                break
            for ds in data.get("data", []) or []:
                ds_id = ds.get("id") or ds.get("slug")
                if ds_id in seen_ds:
                    continue
                seen_ds.add(ds_id)
                slug = ds.get("slug") or slugify(ds.get("title"))
                title = ds.get("title") or slug
                lic = LICENSE_MAP.get((ds.get("license") or "").lower(),
                                      ds.get("license_title"))
                org = (ds.get("organization") or {}).get("name")
                provider = org or title
                for res in ds.get("resources", []) or []:
                    if not is_gtfs_zip_resource(res):
                        continue
                    zurl = res["url"].strip()
                    yield {
                        "id": "%s-%s" % (CC.lower(), slugify(slug)),
                        "provider": provider,
                        "name": title,
                        "cc": CC,
                        "subdiv": None,
                        "city": None,
                        "producer_url": zurl,
                        "hosted_url": None,
                        "license": lic,
                        "bbox": None,
                        "status": "active",
                        "official": True,
                    }
                    break  # one zip per dataset (avoid dated duplicate resources)
            url = data.get("next_page")


DATE_RE = re.compile(r"(\d{2})[-_/](\d{2})[-_/](\d{4})")


def _res_sort_key(res):
    """Rank a CKAN resource so the newest is last; 'Mais Recente' wins."""
    name = (res.get("name") or "").lower()
    recent = 1 if "mais recente" in name else 0
    m = DATE_RE.search(name) or DATE_RE.search(res.get("url") or "")
    if m:
        d, mth, y = m.groups()
        datekey = (int(y), int(mth), int(d))
    else:
        datekey = (0, 0, 0)
    return (recent, datekey, res.get("created") or "")


def scrape_porto():
    """Yield the single latest GTFS zip per Porto CKAN dataset."""
    try:
        data = http_json(PORTO_CKAN)
    except Exception as e:
        print("  Porto CKAN fetch failed: %s" % e)
        return
    for ds in (data.get("result") or {}).get("results", []) or []:
        name_ds = ds.get("name") or ds.get("id")
        title = ds.get("title") or name_ds
        lic = LICENSE_MAP.get((ds.get("license_id") or "").lower(),
                              ds.get("license_title"))
        org = (ds.get("organization") or {}).get("title")
        provider = org or title
        # Guess a human operator/provider from the dataset name/title.
        low_t = (title or "").lower()
        if "stcp" in (name_ds or "") or "stcp" in low_t:
            provider = "STCP — Sociedade de Transportes Colectivos do Porto"
        elif "metro" in low_t:
            provider = "Metro do Porto"

        candidates = []
        for res in ds.get("resources", []) or []:
            fmt = (res.get("format") or "").lower()
            url = (res.get("url") or "").strip()
            if fmt not in ("zip", "gtfs"):
                continue
            if not url.lower().endswith(".zip"):
                continue  # skip truncated '/download/___' style urls
            candidates.append(res)
        if not candidates:
            continue
        best = sorted(candidates, key=_res_sort_key)[-1]
        yield {
            "id": "%s-%s" % (CC.lower(), slugify(name_ds)),
            "provider": provider,
            "name": title,
            "cc": CC,
            "subdiv": "Porto",
            "city": "Porto",
            "producer_url": best["url"].strip(),
            "hosted_url": None,
            "license": lic,
            "bbox": None,
            "status": "active",
            "official": True,
        }


def scrape_direct():
    for f in DIRECT_FEEDS:
        yield {
            "id": "%s-%s" % (CC.lower(), slugify(f["provider"])),
            "provider": f["provider"],
            "name": f["name"],
            "cc": CC,
            "subdiv": f["subdiv"],
            "city": f["city"],
            "producer_url": f["producer_url"],
            "hosted_url": None,
            "license": f["license"],
            "bbox": None,
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

    added = []
    seen_new = set()
    for rec in list(scrape_udata()) + list(scrape_porto()) + list(scrape_direct()):
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