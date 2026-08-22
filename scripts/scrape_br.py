#!/usr/bin/env python3
"""
Brazil (BR) GTFS feed scraper.

Brazil has NO national access point (NAP) and no federal GTFS catalog on
dados.gov.br. Open transit data is fragmented across (1) international
aggregators (Mobility Database, Transitland) that already mirror the biggest
metros, (2) municipal/state CKAN open-data portals with stable resource
download URLs, and (3) login-gated operator portals (SPTrans, Curitiba/URBS)
that we cannot fetch programmatically (use their MDB/Transitland mirrors).

This scraper uses a two-tier strategy:

TIER 1 -- reuse aggregators (best-effort, auth-gated, skipped on failure):
  * Mobility Database:
      GET https://api.mobilitydatabase.org/v1/gtfs_feeds?country_code=BR&limit=200
      Requires a GCIP Bearer token. We read it from env MOBILITYDB_TOKEN, or
      mint one from a refresh token (MOBILITYDB_REFRESH_TOKEN) via the
      access-token endpoint. Each feed object exposes:
        .latest_dataset.hosted_url  -> stable hosted GTFS zip (preferred)
        .source_info.producer_url   -> operator's own GTFS zip
        .locations[].municipality / .subdivision_name / .country_code
        .provider, .feed_name, .license (source_info.license_url)
  * Transitland (alternative cross-check), if TRANSITLAND_APIKEY is set:
      GET https://transit.land/api/v2/rest/feeds?adm0_name=Brazil&per_page=100
      feeds[].urls.static_current -> GTFS zip.

TIER 2 -- exceed MDB via municipal CKAN portals + verified direct URLs
(NO auth; these guarantee the scraper adds feeds even when TIER 1 is empty):
  * CKAN package_search?q=gtfs on each portal, reading
    result.results[].resources[].url for real .zip / CKAN /download URLs.
    Enumerated: dados.pbh.gov.br (Belo Horizonte), dadosabertos.poa.br
    (Porto Alegre), dados.fortaleza.ce.gov.br, dados.recife.pe.gov.br.
  * VERIFIED hardcoded direct feeds (checked live, all HTTP 200 application/zip):
      Belo Horizonte BHTRANS combined/conventional/supplementary (S3, daily),
      ARTESP-SP (all SP metro regions), Porto Alegre EPTC, and
      Rio de Janeiro SMTR (ArcGIS Sharing REST /data endpoint).

LOGIN-GATED, intentionally skipped: SPTrans (developer login) and
Curitiba/URBS (email for creds). Their unauthenticated mirrors surface via
TIER 1 (MDB / Transitland) instead.

Each record appended to data/feeds_full.json has EXACTLY these keys:
  id, provider, name, cc, subdiv, city, producer_url, hosted_url,
  license, bbox, status, official
Dedup is by producer_url (rstrip('/')). Stdlib only.
"""

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

CC = "BR"
UA = "Mozilla/5.0 (compatible; gtfs-catalog/1.0; +https://github.com/jqueguiner/gtfs)"
TIMEOUT = 60

SRC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "feeds_full.json",
)

# ---------------------------------------------------------------------------
# TIER 1 endpoints
# ---------------------------------------------------------------------------
MDB_FEEDS_URL = (
    "https://api.mobilitydatabase.org/v1/gtfs_feeds"
    "?country_code=BR&limit=200"
)
MDB_TOKEN_URL = "https://api.mobilitydatabase.org/v1/tokens"
TRANSITLAND_URL = (
    "https://transit.land/api/v2/rest/feeds"
    "?adm0_name=Brazil&per_page=100"
)

# ---------------------------------------------------------------------------
# TIER 2: municipal / state CKAN portals to enumerate (package_search?q=gtfs)
# ---------------------------------------------------------------------------
CKAN_PORTALS = [
    # (portal_api_base, default_city, default_subdiv)
    ("https://dados.pbh.gov.br", "Belo Horizonte", "Minas Gerais"),
    ("https://dadosabertos.poa.br", "Porto Alegre", "Rio Grande do Sul"),
    ("https://dados.fortaleza.ce.gov.br", "Fortaleza", "Ceará"),
    ("https://dados.recife.pe.gov.br", "Recife", "Pernambuco"),
]

# ---------------------------------------------------------------------------
# TIER 2: VERIFIED direct GTFS zips (checked live: HTTP 200, application/zip).
# These are the backbone that guarantees new feeds regardless of auth state.
# ---------------------------------------------------------------------------
DIRECT_FEEDS = [
    {
        "provider": "BHTrans / SUMOB (Superintendência de Mobilidade)",
        "name": "Belo Horizonte GTFS — convencional (incl. MOVE BRT) + suplementar (daily)",
        "city": "Belo Horizonte",
        "subdiv": "Minas Gerais",
        "producer_url": "https://s3.amazonaws.com/mobilibus-uploads/gtfs/GTFSBHTRANS.zip",
        "license": "CC-BY-4.0",
    },
    {
        "provider": "BHTrans / SUMOB (Superintendência de Mobilidade)",
        "name": "Belo Horizonte GTFS — sistema convencional (incl. MOVE BRT)",
        "city": "Belo Horizonte",
        "subdiv": "Minas Gerais",
        "producer_url": "https://s3.amazonaws.com/mobilibus-uploads/gtfs/GTFSBHTRANSCON.zip",
        "license": "CC-BY-4.0",
    },
    {
        "provider": "BHTrans / SUMOB (Superintendência de Mobilidade)",
        "name": "Belo Horizonte GTFS — sistema suplementar",
        "city": "Belo Horizonte",
        "subdiv": "Minas Gerais",
        "producer_url": "https://s3.amazonaws.com/mobilibus-uploads/gtfs/GTFSBHTRANSSUP.zip",
        "license": "CC-BY-4.0",
    },
    {
        "provider": "ARTESP (Agência de Transporte do Estado de São Paulo)",
        "name": "ARTESP GTFS — all SP-regulated metropolitan regions",
        "city": None,
        "subdiv": "São Paulo",
        "producer_url": (
            "https://dadosabertos.artesp.sp.gov.br/dataset/"
            "92e8bb31-df66-4700-ad9a-42a48f04fb7f/resource/"
            "4c0f3a81-b587-4ead-ab10-4584c02614e0/download/artesp_gtfs.zip"
        ),
        "license": None,
    },
    {
        "provider": "EPTC (Empresa Pública de Transporte e Circulação)",
        "name": "Porto Alegre GTFS — municipal bus network (EPTC)",
        "city": "Porto Alegre",
        "subdiv": "Rio Grande do Sul",
        "producer_url": (
            "https://dadosabertos.poa.br/dataset/"
            "1fe9c2c1-9fbe-48ea-841b-61e30597ecd6/resource/"
            "b3bce61f-78ee-49eb-be57-6236d82bd5e0/download/arquivo-gtfs.zip"
        ),
        "license": "CC-BY-4.0",
    },
    {
        "provider": "SMTR (Secretaria Municipal de Transportes do Rio de Janeiro)",
        "name": "Rio de Janeiro GTFS — municipal bus + BRT (data.rio / SMTR)",
        "city": "Rio de Janeiro",
        "subdiv": "Rio de Janeiro",
        # ArcGIS Sharing REST /data returns the item's GTFS zip directly
        # (item 8ffe62ad... is a CSV Collection named gtfs_rio-de-janeiro.zip).
        "producer_url": (
            "https://www.arcgis.com/sharing/rest/content/items/"
            "8ffe62ad3b2f42e49814bf941654ea6c/data"
        ),
        "license": None,
    },
]

# CKAN license_id -> SPDX-ish label
LICENSE_MAP = {
    "cc-by": "CC-BY-4.0",
    "cc-by-4.0": "CC-BY-4.0",
    "cc-zero": "CC0-1.0",
    "cc-by-sa": "CC-BY-SA-4.0",
    "odc-by": "ODC-BY-1.0",
    "odc-odbl": "ODbL-1.0",
    "notspecified": None,
    "other-open": None,
    "": None,
    None: None,
}


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------
def http_json(url, headers=None, data=None):
    hdrs = {"User-Agent": UA, "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, headers=hdrs, data=body)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def slugify(s):
    s = (s or "").lower()
    # strip accents crudely (stdlib-only, keep it simple)
    for a, b in (("á", "a"), ("â", "a"), ("ã", "a"), ("à", "a"),
                 ("é", "e"), ("ê", "e"), ("í", "i"), ("ó", "o"),
                 ("ô", "o"), ("õ", "o"), ("ú", "u"), ("ç", "c")):
        s = s.replace(a, b)
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "feed"


def is_gtfs_zip_url(url, fmt="", title=""):
    """True if a CKAN resource url is a direct GTFS zip download."""
    low = (url or "").strip().lower()
    if not low or not low.startswith(("http://", "https://")):
        return False
    fmt = (fmt or "").lower()
    blob = (title or "").lower() + " " + low
    # Reject documentation / reference / realtime / non-zip payloads.
    if "developers.google.com" in low or "reference" in low:
        return False
    if re.search(r"gtfs-?rt|realtime|trip-updates|vehicle-positions|/alerts", blob):
        return False
    if fmt in ("html", "url", "json", "geojson", "csv", "pdf"):
        return False
    # Accept a real .zip url, OR a CKAN /download/ path with a zip-ish format.
    if low.endswith(".zip"):
        ok = True
    elif "/download/" in low and (fmt in ("zip", "gtfs") or "gtfs" in blob):
        ok = True
    else:
        ok = False
    if not ok:
        return False
    # Must smell like GTFS (avoid grabbing unrelated shapefile/netex zips).
    if re.search(r"netex|shapefile|\bshp\b|paragens|\.kml", blob):
        return False
    return "gtfs" in blob or fmt == "gtfs" or low.endswith(".zip")


# ---------------------------------------------------------------------------
# TIER 1a: Mobility Database
# ---------------------------------------------------------------------------
def _mdb_token():
    tok = os.environ.get("MOBILITYDB_TOKEN", "").strip()
    if tok:
        return tok
    refresh = os.environ.get("MOBILITYDB_REFRESH_TOKEN", "").strip()
    if not refresh:
        return None
    try:
        resp = http_json(MDB_TOKEN_URL, data={"refresh_token": refresh})
        return (resp.get("access_token") or "").strip() or None
    except Exception as e:
        print("  MDB token mint failed: %s" % e)
        return None


def _mdb_locations(item):
    """Return (city, subdiv) from an MDB feed's locations[]."""
    for loc in item.get("locations") or []:
        if (loc.get("country_code") or "").upper() not in ("BR", ""):
            continue
        return (loc.get("municipality"), loc.get("subdivision_name"))
    locs = item.get("locations") or []
    if locs:
        return (locs[0].get("municipality"), locs[0].get("subdivision_name"))
    return (None, None)


def scrape_mdb():
    token = _mdb_token()
    if not token:
        print("  MDB: no token (set MOBILITYDB_TOKEN or MOBILITYDB_REFRESH_TOKEN) -- skipping TIER 1a")
        return
    try:
        data = http_json(MDB_FEEDS_URL, headers={"Authorization": "Bearer " + token})
    except Exception as e:
        print("  MDB fetch failed: %s" % e)
        return
    # The API may return a bare list, or {"results": [...]} / {"data": [...]}.
    if isinstance(data, dict):
        items = data.get("results") or data.get("data") or data.get("feeds") or []
    else:
        items = data or []
    for item in items:
        if not isinstance(item, dict):
            continue
        src = item.get("source_info") or {}
        latest = item.get("latest_dataset") or {}
        # Prefer the operator's producer_url (matches other scrapers' intent of
        # a direct producer feed); fall back to MDB's hosted mirror.
        producer = (src.get("producer_url") or "").strip()
        hosted = (latest.get("hosted_url") or "").strip()
        url = producer or hosted
        if not url:
            continue
        provider = (item.get("provider") or src.get("producer_url")
                    or "MobilityData (BR feed)")
        name = (item.get("feed_name") or item.get("name")
                or "GTFS feed (Mobility Database)")
        city, subdiv = _mdb_locations(item)
        lic = src.get("license_url") or None
        mdb_id = item.get("id") or item.get("mdb_source_id") or slugify(name)
        yield {
            "id": "%s-mdb-%s" % (CC.lower(), slugify(str(mdb_id))),
            "provider": provider,
            "name": name,
            "cc": CC,
            "subdiv": subdiv,
            "city": city,
            "producer_url": url,
            "hosted_url": hosted or None,
            "license": lic,
            "bbox": None,
            "status": "active",
            "official": True,
        }


# ---------------------------------------------------------------------------
# TIER 1b: Transitland (cross-check)
# ---------------------------------------------------------------------------
def scrape_transitland():
    key = os.environ.get("TRANSITLAND_APIKEY", "").strip()
    if not key:
        print("  Transitland: no TRANSITLAND_APIKEY -- skipping TIER 1b")
        return
    url = TRANSITLAND_URL + "&apikey=" + urllib.parse.quote(key)
    pages = 0
    while url and pages < 10:
        pages += 1
        try:
            data = http_json(url)
        except Exception as e:
            print("  Transitland fetch failed: %s" % e)
            return
        for f in data.get("feeds", []) or []:
            urls = f.get("urls") or {}
            zurl = (urls.get("static_current") or "").strip()
            if not zurl:
                continue
            onestop = f.get("onestop_id") or f.get("id") or slugify(zurl)
            name = ((f.get("name") or "")
                    or (f.get("spec") or "GTFS") + " feed " + str(onestop))
            lic = (f.get("license") or {}).get("spdx_identifier") or None
            yield {
                "id": "%s-tl-%s" % (CC.lower(), slugify(str(onestop))),
                "provider": name or "Transitland (BR feed)",
                "name": name or ("Transitland %s" % onestop),
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
        nxt = ((data.get("meta") or {}).get("next"))
        if nxt:
            url = nxt + ("&apikey=" + urllib.parse.quote(key)
                         if "apikey=" not in nxt else "")
        else:
            url = None


# ---------------------------------------------------------------------------
# TIER 2a: municipal CKAN portals
# ---------------------------------------------------------------------------
def scrape_ckan():
    for base, city, subdiv in CKAN_PORTALS:
        api = base.rstrip("/") + "/api/3/action/package_search?q=gtfs&rows=100"
        try:
            data = http_json(api)
        except Exception as e:
            print("  CKAN %s failed: %s" % (base, e))
            continue
        results = ((data.get("result") or {}).get("results")) or []
        for ds in results:
            ds_name = ds.get("name") or ds.get("id") or "gtfs"
            title = ds.get("title") or ds_name
            lic = LICENSE_MAP.get((ds.get("license_id") or "").lower(),
                                  ds.get("license_title"))
            org = (ds.get("organization") or {}).get("title")
            provider = org or title
            for res in ds.get("resources", []) or []:
                url = (res.get("url") or "").strip()
                if not is_gtfs_zip_url(url, res.get("format"),
                                       res.get("name") or title):
                    continue
                res_id = res.get("id") or slugify(url)
                yield {
                    "id": "%s-%s-%s" % (CC.lower(), slugify(ds_name),
                                        slugify(str(res_id))[:8]),
                    "provider": provider,
                    "name": "%s — %s" % (title, res.get("name") or "GTFS"),
                    "cc": CC,
                    "subdiv": subdiv,
                    "city": city,
                    "producer_url": url,
                    "hosted_url": None,
                    "license": lic,
                    "bbox": None,
                    "status": "active",
                    "official": True,
                }


# ---------------------------------------------------------------------------
# TIER 2b: verified hardcoded direct feeds
# ---------------------------------------------------------------------------
def scrape_direct():
    for f in DIRECT_FEEDS:
        base = slugify(f["provider"])
        tail = slugify(f["name"])[:24]
        yield {
            "id": "%s-%s-%s" % (CC.lower(), base, tail),
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


# ---------------------------------------------------------------------------
# main
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
    sources = (
        list(scrape_mdb())
        + list(scrape_transitland())
        + list(scrape_ckan())
        + list(scrape_direct())
    )
    for rec in sources:
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
