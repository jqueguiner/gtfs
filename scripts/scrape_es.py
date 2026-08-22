#!/usr/bin/env python3
"""Scraper for Spain (ES) open-transit GTFS feeds.

Spain has TWO aggregator layers:

  (1) nap.transportes.gob.es -- the legally-mandated National Access Point
      (EU Delegated Reg. 2017/1926). It is the OFFICIAL enumerator of every
      passenger-transport operator, BUT feed download requires a registered
      login and it exposes NO clean public JSON API (detail pages are
      /Files/Detail/{id}). Not machine-scrapable without a session, so it is
      not used as a programmatic source here.

  (2) datos.gob.es -- the national open-data catalog. Its apidata REST API
      returns DCAT JSON-LD and is the machine-readable path. It is the primary
      source below, supplemented by regional / operator sub-aggregators that
      DO expose clean APIs or stable direct GTFS zips:
         - data-crtm.opendata.arcgis.com  (Madrid CRTM, ArcGIS Hub DCAT)
         - data.renfe.com                 (national rail, CKAN)
         - direct operator GTFS zips       (EMT Madrid/Malaga, AMB, Bizkaibus, ...)

Response shapes (verified live):

  datos.gob.es apidata (JSON-LD DCAT):
    GET https://datos.gob.es/apidata/catalog/dataset/keyword/gtfs.json?_pageSize=200&_page=0
    -> result.items[] ; each item has:
         title        -> [{"_value": "...", "_lang": "es"}]  (or dict / str)
         distribution -> [{"accessURL": "...", "format": {"value": "..."}}, ...]
    The 'gtfs' keyword is NOISY (per-file CSV/JSON splits like Alcobendas'
    stoptimes_json.zip). We keep only distributions whose accessURL ends in
    '.zip' AND drop obvious per-table / split names.

  Madrid CRTM ArcGIS Hub DCAT-US 1.1:
    GET https://data-crtm.opendata.arcgis.com/api/feed/dcat-us/1.1.json
    -> dataset[] ; GTFS datasets are titled 'GTFS ...' and carry
       identifier = 'https://www.arcgis.com/home/item.html?id=<ITEMID>'.
    The direct GTFS zip for an ArcGIS item is:
       https://www.arcgis.com/sharing/rest/content/items/<ITEMID>/data
    (verified: returns application/zip, PK.. signature).

  Renfe CKAN:
    GET https://data.renfe.com/api/3/action/package_search?fq=res_format:GTFS
    -> result.results[].resources[] where format==GTFS -> .url is the zip.

stdlib only (json, urllib.request, os, re). Appends to data/feeds_full.json
(a JSON array). Dedup by producer_url.rstrip('/'). Robust: every network call
is wrapped, failures are skipped, the run never aborts.
"""
import json
import os
import re
import ssl
import urllib.request

CC = "ES"
SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'feeds_full.json')

UA = "gtfs-catalog-scraper/1.0 (+https://github.com/jqueguiner/gtfs)"
TIMEOUT = 45

DATOS_URL = "https://datos.gob.es/apidata/catalog/dataset/keyword/gtfs.json?_pageSize=200&_page={page}"
CRTM_DCAT = "https://data-crtm.opendata.arcgis.com/api/feed/dcat-us/1.1.json"
ARCGIS_ITEM_DATA = "https://www.arcgis.com/sharing/rest/content/items/{item}/data"
RENFE_CKAN = "https://data.renfe.com/api/3/action/package_search?fq=res_format:GTFS&rows=100"

# accept TLS quirks on a couple of gov hosts without aborting
_SSL = ssl.create_default_context()
_SSL.check_hostname = False
_SSL.verify_mode = ssl.CERT_NONE

# Distribution accessURLs whose filename matches these are per-table / split
# exports, NOT a complete GTFS feed -> reject.
_SPLIT_RE = re.compile(
    r"(stop_?times|stoptimes|_json|calendar|_csv|routes|trips|shapes|agency|"
    r"documentacion|explicacion)",
    re.IGNORECASE,
)


def slugify(s):
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "feed"


def _text(v):
    """Normalize a DCAT multilingual title into a plain string."""
    if isinstance(v, list):
        for x in v:
            if isinstance(x, dict) and x.get("_value"):
                return x["_value"]
        return v[0] if v and isinstance(v[0], str) else ""
    if isinstance(v, dict):
        return v.get("_value", "")
    return v or ""


def load_existing():
    if not os.path.exists(SRC):
        return []
    try:
        with open(SRC, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (ValueError, OSError):
        return []


def fetch_json(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=_SSL) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def rec(provider, name, subdiv, city, url, license_, slug=None):
    """Build a catalog record in the exact repo schema.

    `slug` (if given) is the unique per-feed id discriminator; otherwise it is
    derived from provider + locality. IDs must be unique per feed, so callers
    that emit several feeds for one provider (e.g. CRTM's 6 modes) pass an
    explicit slug.
    """
    base = slug if slug else (provider + "-" + (city or subdiv or name))
    return {
        "id": "{}-{}".format(CC.lower(), slugify(base)),
        "provider": provider,
        "name": name,
        "cc": CC,
        "subdiv": subdiv,
        "city": city,
        "producer_url": url,
        "hosted_url": None,
        "license": license_,
        "bbox": None,
        "status": "active",
        "official": True,
    }


# ---------------------------------------------------------------------------
# Source 1: datos.gob.es apidata (DCAT JSON-LD)
# ---------------------------------------------------------------------------
def from_datos_gob():
    out = []
    page = 0
    seen_pages = 0
    while page < 10:  # hard cap; keyword=gtfs is small (~37 items, one page)
        try:
            d = fetch_json(DATOS_URL.format(page=page))
        except Exception as e:
            print("WARN datos.gob.es page {} failed: {}".format(page, e))
            break
        items = (d.get("result") or {}).get("items") or []
        if not items:
            break
        seen_pages += 1
        for it in items:
            title = _text(it.get("title")) or _text(it.get("description")) or "GTFS"
            dists = it.get("distribution") or []
            if isinstance(dists, dict):
                dists = [dists]
            for dist in dists:
                au = (dist.get("accessURL") or "").strip()
                if not au:
                    continue
                path = au.split("?")[0]
                if not path.lower().endswith(".zip"):
                    continue
                fname = path.rsplit("/", 1)[-1]
                # reject per-table / split exports masquerading as .zip
                if _SPLIT_RE.search(fname):
                    continue
                # host + zip filename -> compact unique slug
                host = re.sub(r"^www\.", "", path.split("/")[2]) if "//" in path else ""
                stem = re.sub(r"\.zip$", "", fname, flags=re.IGNORECASE)
                out.append(rec(
                    provider=title,
                    name="{} (GTFS, datos.gob.es)".format(title),
                    subdiv=None,
                    city=None,
                    url=au,
                    license_="Open data (datos.gob.es / DCAT-AP-ES)",
                    slug="{}-{}".format(host.split(".")[0], stem),
                ))
        nxt = (d.get("result") or {}).get("next")
        if not nxt:
            break
        page += 1
    print("  datos.gob.es: {} zip GTFS distribution(s) over {} page(s)".format(len(out), seen_pages))
    return out


# ---------------------------------------------------------------------------
# Source 2: Madrid CRTM ArcGIS Hub DCAT-US
# ---------------------------------------------------------------------------
_ITEM_RE = re.compile(r"id=([0-9a-fA-F]{32})")


def from_crtm():
    out = []
    try:
        d = fetch_json(CRTM_DCAT)
    except Exception as e:
        print("WARN CRTM ArcGIS DCAT failed: {}".format(e))
        return out
    for it in d.get("dataset") or []:
        title = it.get("title") or ""
        if not title.lower().startswith("gtfs"):
            continue
        ident = it.get("identifier") or ""
        m = _ITEM_RE.search(ident)
        if not m:
            # fall back to any distribution downloadURL, else skip
            continue
        item_id = m.group(1)
        url = ARCGIS_ITEM_DATA.format(item=item_id)
        lic = it.get("license") or "CRTM licencia de uso (open)"
        out.append(rec(
            provider="CRTM - Consorcio Regional de Transportes de Madrid",
            name=title,
            subdiv="Comunidad de Madrid",
            city="Madrid",
            url=url,
            license_=lic if isinstance(lic, str) else "CRTM licencia de uso (open)",
            slug="crtm-" + slugify(title.replace("GTFS", "").strip() or item_id),
        ))
    print("  CRTM ArcGIS: {} GTFS dataset(s)".format(len(out)))
    return out


# ---------------------------------------------------------------------------
# Source 3: Renfe CKAN (national rail)
# ---------------------------------------------------------------------------
def from_renfe():
    out = []
    try:
        d = fetch_json(RENFE_CKAN)
    except Exception as e:
        print("WARN Renfe CKAN failed: {}".format(e))
        return out
    for pkg in (d.get("result") or {}).get("results") or []:
        ptitle = pkg.get("title") or pkg.get("name") or "Renfe GTFS"
        for r in pkg.get("resources") or []:
            fmt = (r.get("format") or "").upper()
            url = (r.get("url") or "").strip()
            if not url:
                continue
            if fmt == "GTFS" or url.lower().split("?")[0].endswith(".zip"):
                out.append(rec(
                    provider="Renfe",
                    name=ptitle,
                    subdiv=None,
                    city=None,
                    url=url,
                    license_="Open data (Renfe / data.renfe.com)",
                ))
    print("  Renfe CKAN: {} GTFS resource(s)".format(len(out)))
    return out


# ---------------------------------------------------------------------------
# Source 4: curated, verified direct operator GTFS zips
# (operators the machine APIs above don't surface with a clean direct zip).
# ---------------------------------------------------------------------------
CURATED = [
    ("EMT Madrid", "EMT Madrid GTFS (municipal buses)", "Comunidad de Madrid", "Madrid",
     "https://servicios.emtmadrid.es:8443/gtfs/transitemt.zip",
     "Open data (EMT Madrid / datos.emtmadrid.es)"),
    ("EMT Malaga - Empresa Malaguena de Transportes", "EMT Malaga GTFS (city buses)", "Andalucia", "Malaga",
     "http://datosabiertos.malaga.eu/recursos/transporte/EMT/lineasYHorarios/google_transit_txt.zip",
     "Open data (Ayuntamiento de Malaga)"),
    ("Bizkaibus", "Bizkaibus GTFS (Biscay regional buses)", "Pais Vasco", "Bilbao",
     "https://baliabideak.bizkaia.eus/Bizkaibus/GTFS/Bizkaibus.zip",
     "Open data (Diputacion Foral de Bizkaia)"),
    ("AMB - Area Metropolitana de Barcelona", "AMB GTFS (metropolitan buses)", "Cataluna", "Barcelona",
     "http://www.amb.cat/Mobilitat/OpenData/google_transit.zip",
     "Open data (AMB)"),
    ("DBUS - Compania del Tranvia de San Sebastian", "DBUS GTFS (Donostia city buses)", "Pais Vasco", "San Sebastian",
     "ftp://ftp.geo.euskadi.net/cartografia/Transporte/Moveuskadi/ATTG/dbus/google_transit.zip",
     "Open Data Euskadi"),
    ("TMB - Transports Metropolitans de Barcelona", "TMB GTFS (metro + bus; requires app_id/app_key)", "Cataluna", "Barcelona",
     "https://api.tmb.cat/v1/static/datasets/gtfs.zip",
     "TMB open data (registration required)"),
]


def from_curated():
    out = [rec(p, n, sd, c, u, lic) for (p, n, sd, c, u, lic) in CURATED]
    print("  curated direct feeds: {}".format(len(out)))
    return out


def main():
    existing = load_existing()
    seen = set()
    for r in existing:
        pu = r.get("producer_url")
        if pu:
            seen.add(pu.rstrip("/"))

    candidates = []
    candidates += from_datos_gob()
    candidates += from_crtm()
    candidates += from_renfe()
    candidates += from_curated()

    added = 0
    for r in candidates:
        url = r.get("producer_url") or ""
        key = url.rstrip("/")
        if not key or key in seen:
            continue
        seen.add(key)
        existing.append(r)
        added += 1

    os.makedirs(os.path.dirname(SRC), exist_ok=True)
    with open(SRC, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    print("+{} new {} feeds".format(added, CC))


if __name__ == "__main__":
    main()
