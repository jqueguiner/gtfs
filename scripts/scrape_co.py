#!/usr/bin/env python3
"""
Colombia (CO) GTFS feed scraper.

Source
------
Colombia has NO EU-style legally-mandated National Access Point and no single
national bulk GTFS list. The national open-data portal datos.gov.co (Socrata)
federates exactly ONE GTFS dataset (Bogota SITP, id nysb-4689) that merely
points back to the operator's own portal.

In practice every Colombian operator that publishes open GTFS does so on its own
Esri / ArcGIS Hub open-data portal (datosabiertos-transmilenio.hub.arcgis.com,
datosabiertos-metrodemedellin.opendata.arcgis.com, the Metrocali hub). All of
those Hub items are indexed by the shared ArcGIS Online *sharing REST* API, which
is therefore the de-facto machine-readable national aggregator.

Discovery / resolution (done live, nothing hardcoded except seed queries)
-------------------------------------------------------------------------
Step 1 - discover:
    GET https://www.arcgis.com/sharing/rest/search?q=<Q>&f=json&num=100
    over several queries (generic + per-operator). Dedupe items by id. Keep
    items whose title contains 'GTFS' and whose type is 'Document Link' or
    'CSV Collection' (Feature Services, StoryMaps, etc. are not downloadable
    GTFS feeds and are skipped).

Step 2 - group + pick newest:
    Operators publish one dated/yearly item per release (TransMilenio: dated
    'GTFS Estaticos YYYY-MM-DD' Document Links; Metro de Medellin: yearly
    'GTFS-Metro de Medellin YYYY' CSV Collections). We group kept items by
    owner (== operator) and keep only the single newest item per owner, ranked
    by the date parsed from its title (falls back to the item 'modified' epoch).
    Emitting every historical dated item would be pure duplication.

Step 3 - resolve the download URL (differs by ArcGIS item type):
    * 'Document Link'  -> the item's own 'url' field is the real hosted zip
      (TransMilenio -> a stable Google Cloud Storage zip
      https://storage.googleapis.com/gtfs-estaticos/GTFS_YYYYMMDD.zip ;
      Cali/Metrocali -> its self-hosted endpoint). For these items the ArcGIS
      /data resolver returns an empty JSON (no uploaded file), so the 'url'
      field IS the producer_url. Items with an empty 'url' are skipped.
    * 'CSV Collection' -> the file is uploaded to the item, so the download is
      https://www.arcgis.com/sharing/rest/content/items/{id}/data (verified to
      stream application/zip, e.g. Medellin -> GTFS-Metro_de_Medellin_2025.zip,
      ~2.5 MB). We use that /data resolver as the producer_url.

Step 4 - also poll the national Socrata catalog for any newly federated GTFS:
    GET http://api.us.socrata.com/api/catalog/v1?domains=www.datos.gov.co&q=GTFS
    Any result carrying a direct .zip access point is emitted too (future-proof;
    today it only federates Bogota which is already covered above, and is deduped
    by producer_url).

Only Bogota (TransMilenio), Medellin (Metro de Medellin) and Cali (Metrocali /
MIO) have confirmed open GTFS today; other BRT cities (Barranquilla/Transmetro,
Bucaramanga/Metrolinea, Pereira/Megabus, Cartagena/Transcaribe) publish open-data
pages but no GTFS package, so the aggregator exposes no feed for them and none is
emitted.

Each record appended to data/feeds_full.json has EXACTLY these keys:
  id, provider, name, cc, subdiv, city, producer_url, hosted_url,
  license, bbox, status, official
Dedup is by producer_url (rstrip('/')). Stdlib only.
"""

import json
import os
import re
import urllib.request

CC = "CO"
UA = "Mozilla/5.0 (compatible; gtfs-catalog/1.0; +https://github.com/jqueguiner/gtfs)"
TIMEOUT = 60

SRC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "feeds_full.json",
)

ARCGIS_SEARCH = "https://www.arcgis.com/sharing/rest/search?q=%s&f=json&num=100"
ARCGIS_ITEM = "https://www.arcgis.com/sharing/rest/content/items/%s?f=json"
ARCGIS_DATA = "https://www.arcgis.com/sharing/rest/content/items/%s/data"

# Seed queries fed to the ArcGIS sharing REST search. Generic + per-operator so
# no single operator is missed if the generic 'GTFS Colombia' page is crowded
# out by unrelated global Esri transit layers. Each form below was verified to
# actually surface its operator against the live sharing REST API (owner: is
# case-sensitive; multi-token free-text is AND-ed, so bad token combos return
# 0 — hence the deliberate use of owner: filters for Medellin and Cali).
QUERIES = (
    "GTFS Colombia",
    "GTFS SITP transmilenio",       # -> david.monroy_Transmilenio + SecretariaMovilidad
    "GTFS Estaticos",               # -> TransMilenio dated Document Links
    "owner:gsig_metromed",          # -> Metro de Medellin yearly CSV Collections
    "GTFS Medellín",                # -> Metro de Medellin (accent-bearing fallback)
    "owner:Metrocali GTFS",         # -> Metrocali / MIO Cali Document Link
)

# ArcGIS item types that resolve to a real downloadable GTFS feed.
KEEP_TYPES = ("Document Link", "CSV Collection")

# owner (ArcGIS username) -> operator metadata. Owners not listed still get a
# best-effort record built from item fields; this table just supplies clean
# provider / city / subdivision / license where we know them.
OWNER_META = {
    "david.monroy_transmilenio": {
        "provider": "TransMilenio S.A.",
        "city": "Bogota",
        "subdiv": "Bogota D.C.",
        "license": "CC-BY-SA-4.0",
        "sys": "TransMilenio BRT + SITP zonal buses + TransMiCable",
    },
    "secretariamovilidad": {
        "provider": "Secretaria Distrital de Movilidad de Bogota",
        "city": "Bogota",
        "subdiv": "Bogota D.C.",
        "license": "CC-BY-SA-4.0",
        "sys": "SITP integrated public transport",
    },
    "gsig_metromed": {
        "provider": "Metro de Medellin Ltda.",
        "city": "Medellin",
        "subdiv": "Antioquia",
        "license": None,
        "sys": "SITVA: Metro, Metrocable, Tranvia + integrated feeder buses",
    },
    "metrocali": {
        "provider": "Metro Cali S.A. (MIO)",
        "city": "Cali",
        "subdiv": "Valle del Cauca",
        "license": None,
        "sys": "MIO BRT + padron/complementary + alimentador feeder buses",
    },
}

SOCRATA_CATALOG = (
    "http://api.us.socrata.com/api/catalog/v1"
    "?domains=www.datos.gov.co&q=GTFS"
)


def http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def slugify(s):
    s = (s or "").lower()
    # strip accents crudely so slugs stay ascii-clean
    for a, b in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"),
                 ("ñ", "n"), ("ü", "u")):
        s = s.replace(a, b)
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "feed"


_DATE_RE = re.compile(r"(20\d{2})[-/ ]?(\d{1,2})?[-/ ]?(\d{1,2})?")


def title_rank(title):
    """Return a comparable (year, month, day) tuple parsed from an item title
    like 'GTFS Estaticos 2026-07-22' or 'GTFS Metro de Medellin 2025'.
    Missing month/day default to 0 so a bare year still sorts by year."""
    m = _DATE_RE.search(title or "")
    if not m:
        return (0, 0, 0)
    y = int(m.group(1))
    mo = int(m.group(2)) if m.group(2) else 0
    da = int(m.group(3)) if m.group(3) else 0
    if mo > 12:
        mo = 0
    if da > 31:
        da = 0
    return (y, mo, da)


def is_gtfs_item(it):
    title = (it.get("title") or "")
    if "gtfs" not in title.lower():
        return False
    return it.get("type") in KEEP_TYPES


def discover_items():
    """Run every seed query, collect GTFS Document Link / CSV Collection items,
    deduped by id."""
    by_id = {}
    for q in QUERIES:
        url = ARCGIS_SEARCH % urllib.request.quote(q)
        try:
            data = http_json(url)
        except Exception as e:
            print("  search '%s' failed: %s" % (q, e))
            continue
        for it in data.get("results", []) or []:
            if not is_gtfs_item(it):
                continue
            iid = it.get("id")
            if iid and iid not in by_id:
                by_id[iid] = it
    return list(by_id.values())


def newest_per_owner(items):
    """Group kept items by owner and keep only the newest per owner."""
    best = {}
    for it in items:
        owner = (it.get("owner") or "").strip()
        key = owner.lower() or (it.get("id") or "")
        rank = (title_rank(it.get("title")), it.get("modified") or 0)
        cur = best.get(key)
        if cur is None or rank > cur[0]:
            best[key] = (rank, it)
    return [v[1] for v in best.values()]


def resolve_download(it):
    """Return the producer_url (direct GTFS zip) for a kept item, or None.

    Document Link -> the item's own 'url' field is the real hosted zip.
    CSV Collection -> the uploaded file at the /data resolver.
    We fetch the item detail to read a reliable 'url' (search snippets can omit
    it), then fall back to the /data resolver.
    """
    iid = it.get("id")
    itype = it.get("type")
    url = (it.get("url") or "").strip()
    lic_url = None
    if not url or itype == "Document Link":
        # fetch full item metadata for the authoritative url / licenseInfo
        try:
            detail = http_json(ARCGIS_ITEM % iid)
            url = (detail.get("url") or url or "").strip()
            lic_url = (detail.get("licenseInfo") or "").strip() or None
        except Exception as e:
            print("  item detail %s failed: %s" % (iid, e))

    if itype == "Document Link":
        # For a Document Link the payload lives at the linked url, not /data.
        if url:
            return url, lic_url
        return None, lic_url

    if itype == "CSV Collection":
        # The GTFS zip is uploaded to the item; the /data endpoint streams it.
        return ARCGIS_DATA % iid, lic_url

    return None, lic_url


def build_record(it, producer_url, lic_from_item):
    owner = (it.get("owner") or "").strip().lower()
    meta = OWNER_META.get(owner, {})
    title = it.get("title") or "GTFS"
    provider = meta.get("provider") or owner or "Unknown operator"
    city = meta.get("city")
    sys = meta.get("sys")
    lic = meta.get("license")
    if lic is None:
        lic = lic_from_item  # honour any licenseInfo the item itself declared

    name = "%s — %s" % (title, provider)
    if sys:
        name += " (%s)" % sys

    # id: co-<operator-slug> so successive dated releases of the same operator
    # keep a stable id (only the newest is emitted anyway).
    op_slug = slugify(meta.get("provider") or owner or title)
    rid = "%s-%s" % (CC.lower(), op_slug)

    return {
        "id": rid,
        "provider": provider,
        "name": name,
        "cc": CC,
        "subdiv": meta.get("subdiv"),
        "city": city,
        "producer_url": producer_url,
        "hosted_url": None,
        "license": lic,
        "bbox": None,
        "status": "active",
        "official": True,
    }


def scrape_arcgis():
    items = discover_items()
    print("  ArcGIS: %d GTFS Document Link / CSV Collection items discovered"
          % len(items))
    for it in newest_per_owner(items):
        producer_url, lic_url = resolve_download(it)
        if not producer_url:
            print("  skip (no download url): %s [%s]"
                  % (it.get("title"), it.get("type")))
            continue
        yield build_record(it, producer_url, lic_url)


def scrape_socrata():
    """Emit any GTFS dataset federated on datos.gov.co that carries a direct
    .zip access point. Future-proofing; deduped by producer_url."""
    try:
        data = http_json(SOCRATA_CATALOG)
    except Exception as e:
        print("  Socrata catalog fetch failed: %s" % e)
        return
    for res in data.get("results", []) or []:
        meta = res.get("metadata") or {}
        aps = []
        ap = meta.get("access_points")
        if isinstance(ap, dict):
            aps.extend(ap.values())
        elif isinstance(ap, str):
            aps.append(ap)
        for extra in (meta.get("additional_access_points") or []):
            if isinstance(extra, dict):
                v = extra.get("urls") or extra.get("url")
                if isinstance(v, dict):
                    aps.extend(v.values())
                elif isinstance(v, str):
                    aps.append(v)
        zurl = None
        for u in aps:
            if isinstance(u, str) and u.lower().endswith(".zip"):
                zurl = u.strip()
                break
        if not zurl:
            continue
        r = res.get("resource") or {}
        title = r.get("name") or "GTFS"
        yield {
            "id": "%s-socrata-%s" % (CC.lower(), slugify(r.get("id") or title)),
            "provider": "datos.gov.co (federated)",
            "name": title,
            "cc": CC,
            "subdiv": None,
            "city": None,
            "producer_url": zurl,
            "hosted_url": None,
            "license": None,
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
    for rec in list(scrape_arcgis()) + list(scrape_socrata()):
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
