#!/usr/bin/env python3
"""
Italy (IT) GTFS feed scraper.

Source: dati.gov.it national open-data catalog (CKAN 3 API) -- the de-facto
national GTFS enumerator. The legally-mandated NAP at cciss.it is NeTEx/SIRI
only (not GTFS) and is intentionally NOT scraped here.

  GET https://www.dati.gov.it/opendata/api/3/action/package_search?q=gtfs&rows=200

For every dataset we take .organization.title as the publisher/operator and
iterate .resources[], keeping the ones that point at a real GTFS .zip / .gtfs
download. We skip:
  * GTFS-RT .aspx endpoints
  * true .7z / incrementDownload.action / geospatial-map / NeTEx resources
  * Roma "rete_trasporto_DD.MM.YYYY" historical dated snapshots
  * Google-Drive /view links and cloud mirror snapshots of past years
  * Palermo's ~100 period-specific historical snapshots (keep only the newest)

Appends records to data/feeds_full.json in the exact repo schema, dedup by
producer_url (rstrip('/')). stdlib only.
"""
import json
import os
import re
import urllib.request

CC = "IT"
API_URL = "https://www.dati.gov.it/opendata/api/3/action/package_search?q=gtfs&rows={rows}&start={start}"
ROWS = 200
UA = "Mozilla/5.0 (compatible; gtfs-catalog-bot/1.0)"
TIMEOUT = 90

SRC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "feeds_full.json",
)

# a DD.MM.YYYY / DD_MM_YYYY / DD-MM-YYYY stamp inside a download filename -> snapshot
DATED_FILE = re.compile(r"\d{1,2}[._-]\d{1,2}[._-]\d{4}")
# a period / month / year marker inside a dataset TITLE -> historical snapshot
PERIOD = re.compile(
    r"\d{2}/\d{2}/\d{4}|20\d\d|GENNAIO|FEBBRAIO|MARZO|APRILE|MAGGIO|GIUGNO|"
    r"LUGLIO|AGOSTO|SETTEMBRE|OTTOBRE|NOVEMBRE|DICEMBRE|PERIODO",
    re.I,
)
# markers of an older/mirror copy in a RESOURCE name (year ranges, "20xx-20xx")
OLD_RES = re.compile(r"20\d\d\s*[-–]\s*20\d\d|20\d\d")

# region hints per publisher, for the subdiv + city columns
REGION_BY_ORG = {
    "Comune di Milano": ("Lombardia", "Milan"),
    "Regione Lombardia": ("Lombardia", None),
    "Comune di Torino": ("Piemonte", "Turin"),
    "Roma Capitale": ("Lazio", "Rome"),
    "Comune di Genova": ("Liguria", "Genoa"),
    "Regione Liguria": ("Liguria", None),
    "Regione Toscana": ("Toscana", None),
    "Provincia Autonoma di Trento": ("Trentino-Alto Adige", "Trento"),
    "Regione Puglia": ("Puglia", None),
    "Regione Calabria": ("Calabria", None),
    "Comune di Messina": ("Sicilia", "Messina"),
    "Comune di Palermo": ("Sicilia", "Palermo"),
    "Comune di Matera": ("Basilicata", "Matera"),
    "Comune di Lecce": ("Puglia", "Lecce"),
}


def slugify(s):
    s = (s or "").lower()
    s = s.replace("à", "a").replace("è", "e").replace("é", "e")
    s = s.replace("ì", "i").replace("ò", "o").replace("ù", "u")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def is_gtfs_resource(r):
    """True if this resource is a real, current GTFS zip/.gtfs download."""
    u = (r.get("url") or "").strip()
    if not u:
        return False
    fmt = (r.get("format") or "").upper()
    lu = u.lower()
    tail = lu.split("?")[0].rsplit("/", 1)[-1]  # download filename

    # non-GTFS / non-static / mirror endpoints
    if lu.endswith(".aspx"):
        return False
    if "incrementdownload.action" in lu:
        return False
    if "geospatial" in lu or "/api/geospatial" in lu:
        return False
    if "netex" in lu:
        return False
    if "drive.google.com" in lu and "/view" in lu:
        return False  # not a direct download
    if "fermate" in lu or "shapefile" in lu or "v_mob_" in lu:
        return False  # stops-only GIS shapefile, not a GTFS feed

    # true .7z archives are skipped; a ".gtfs" extension is kept even when the
    # catalog mislabels its format as 7Z (Toscana colbus/at-scolastico)
    if tail.endswith(".7z"):
        return False

    is_zip = tail.endswith(".zip")
    is_gtfs_ext = tail.endswith(".gtfs")
    if not (is_zip or is_gtfs_ext or fmt in ("GTFS", "ZIP")):
        return False

    # Roma dated historical snapshot (rete_trasporto_08.09.2020.zip etc.)
    if DATED_FILE.search(tail):
        return False
    return True


def region_for(org, url):
    for key, (sub, city) in REGION_BY_ORG.items():
        if key.lower() in (org or "").lower():
            return sub, city
    h = (url or "").lower()
    if "comune.bari" in h:
        return "Puglia", "Bari"
    if "comune.lecce" in h:
        return "Puglia", "Lecce"
    return None, None


def fetch_datasets():
    """Paginate the CKAN API and return all dataset dicts."""
    out = []
    start = 0
    while True:
        url = API_URL.format(rows=ROWS, start=start)
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                data = json.load(resp)
        except Exception as e:
            print("  ! fetch failed at start=%d: %s" % (start, e))
            break
        if not data.get("success"):
            break
        result = data.get("result", {})
        batch = result.get("results", []) or []
        out.extend(batch)
        count = result.get("count", 0)
        start += ROWS
        if start >= count or not batch:
            break
    return out


def _make_record(org, title, url, lic, sub, city, rname):
    feed_name = title
    if rname and rname.lower() not in ("", "gtfs") and not rname.lower().startswith("dati "):
        feed_name = "%s -- %s" % (title, rname)

    tail = url.split("?")[0].rsplit("/", 1)[-1]
    stem = re.sub(r"\.(zip|gtfs)$", "", tail, flags=re.I)
    if stem and stem not in ("gtfs", "google_transit", "download"):
        slug_src = stem
    else:
        slug_src = rname or title
    slug = slugify("%s-%s" % (org, slug_src))[:80] or slugify(org)

    return {
        "id": "%s-%s" % (CC.lower(), slug),
        "provider": org,
        "name": feed_name,
        "cc": CC,
        "subdiv": sub,
        "city": city,
        "producer_url": url,
        "hosted_url": None,
        "license": lic,
        "bbox": None,
        "status": "active",
        "official": True,
    }


def build_records(datasets):
    records = []
    palermo_snaps = []  # (sort_key, record) -- keep only newest

    for ds in datasets:
        title = ds.get("title") or ""
        org = (ds.get("organization") or {}).get("title") or "Unknown"
        lic = ds.get("license_title") or ds.get("license_id") or None
        modified = ds.get("metadata_modified") or ds.get("issued") or ""

        for r in ds.get("resources", []):
            if not is_gtfs_resource(r):
                continue
            url = (r.get("url") or "").strip()
            rname = r.get("name") or ""

            # Palermo publishes ~100 period-specific historical snapshots; keep
            # only the single most-recently-modified one.
            if "palermo" in org.lower() and PERIOD.search(title):
                sub, city = region_for(org, url)
                rec = _make_record(org, title, url, lic, sub, city, rname)
                palermo_snaps.append((modified, rec))
                continue

            # skip explicit historical-mirror resources (year ranges in name)
            if OLD_RES.search(rname) and "aggiorn" not in rname.lower():
                continue

            sub, city = region_for(org, url)
            records.append(_make_record(org, title, url, lic, sub, city, rname))

    if palermo_snaps:
        palermo_snaps.sort(key=lambda x: x[0], reverse=True)
        records.append(palermo_snaps[0][1])

    return records


def main():
    with open(SRC, "r", encoding="utf-8") as f:
        existing = json.load(f)

    seen = {(e.get("producer_url") or "").rstrip("/") for e in existing}
    seen_ids = {e.get("id") for e in existing}

    datasets = fetch_datasets()
    print("fetched %d datasets from dati.gov.it" % len(datasets))

    candidates = build_records(datasets)

    new = []
    local_seen = set()
    for rec in candidates:
        key = rec["producer_url"].rstrip("/")
        if key in seen or key in local_seen:
            continue
        local_seen.add(key)
        rid = rec["id"]
        n = 2
        while rid in seen_ids:
            rid = "%s-%d" % (rec["id"], n)
            n += 1
        rec["id"] = rid
        seen_ids.add(rid)
        new.append(rec)

    if new:
        existing.extend(new)
        with open(SRC, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

    print("+%d new %s feeds" % (len(new), CC))


if __name__ == "__main__":
    main()