#!/usr/bin/env python3
"""Scraper for Austria (AT) open-transit GTFS feeds.

Source: Mobilitätsverbünde Österreich (MVO) Data Provisioning Platform
        https://data.mobilitaetsverbuende.at  (national GTFS aggregator; the
        operational hub for all 7 regional Verkehrsverbünde + nationwide rail).

The catalog API is fully open (placeholder bearer token works for metadata):
    GET .../api/public/v1/data-sets?tagFilterModeInclusive=true
Each dataset exposes id, nameEn, license and
    activeVersions[0].dataSetVersion.id (versionId) + .file.originalName.
GTFS feeds are the ones whose originalName matches /_gtfs_.*_2026\\.zip$/.

The canonical direct-download URL for each dataset version is
    .../api/public/v1/data-sets/versions/{versionId}/file
NOTE: downloading the actual zip returns HTTP 401 with the placeholder token;
a free registered MVO token (license acceptance) is required to fetch bytes.
The catalog/metadata is scrapable without auth, so we record the direct
producer_url from the open metadata.

Additionally Vienna's Wiener Linien is a SEPARATE direct no-auth GTFS zip.

stdlib only. Appends records to data/feeds_full.json (a JSON array).
"""
import json
import os
import re
import urllib.request

CC = "AT"
API_URL = "https://data.mobilitaetsverbuende.at/api/public/v1/data-sets?tagFilterModeInclusive=true"
FILE_URL_TMPL = "https://data.mobilitaetsverbuende.at/api/public/v1/data-sets/versions/{vid}/file"
GTFS_RE = re.compile(r"_gtfs_.*_2026\.zip$", re.IGNORECASE)
SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'feeds_full.json')

# Map the verbund/EVU token embedded in the GTFS filename -> region + city + provider.
# token is the segment right before "_2026" (may be prefixed by "flex_").
VERBUND = {
    "vor": {
        "provider": "Verkehrsverbund Ost-Region (VOR)",
        "subdiv": "Vienna / Lower Austria / Burgenland",
        "city": "Vienna",
    },
    "verbundlinie": {
        "provider": "Verkehrsverbund Steiermark (Verbund Linie)",
        "subdiv": "Styria",
        "city": "Graz",
    },
    "salzburgverkehr": {
        "provider": "Salzburger Verkehrsverbund (Salzburg Verkehr)",
        "subdiv": "Salzburg",
        "city": "Salzburg",
    },
    "kaerntnerlinien": {
        "provider": "Verkehrsverbund Kärnten (Kärntner Linien)",
        "subdiv": "Carinthia",
        "city": "Klagenfurt",
    },
    "ooevv": {
        "provider": "Oberösterreichischer Verkehrsverbund (OÖVV)",
        "subdiv": "Upper Austria",
        "city": "Linz",
    },
    "vvt": {
        "provider": "Verkehrsverbund Tirol (VVT / IVB)",
        "subdiv": "Tyrol",
        "city": "Innsbruck",
    },
    "vmobil": {
        "provider": "Verkehrsverbund Vorarlberg (VMOBIL)",
        "subdiv": "Vorarlberg",
        "city": "Bregenz",
    },
    "esg": {
        "provider": "Linz AG Linien",
        "subdiv": "Upper Austria",
        "city": "Linz",
    },
    "evu": {
        "provider": "ÖBB-Personenverkehr / EVU (nationwide rail)",
        "subdiv": None,
        "city": None,
    },
}


def slugify(s):
    s = s.lower()
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


def fetch_catalog():
    req = urllib.request.Request(
        API_URL,
        headers={
            "Accept": "application/json",
            "Authorization": "Bearer any",
            "User-Agent": "gtfs-catalog-scraper/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode("utf-8", "replace")
    data = json.loads(raw)
    # API may return a bare array or a wrapper; normalize to a list.
    if isinstance(data, dict):
        for k in ("data", "content", "items", "dataSets", "results"):
            if isinstance(data.get(k), list):
                return data[k]
        return []
    return data if isinstance(data, list) else []


def token_from_filename(name):
    """Extract the verbund/EVU token that sits before _2026.zip.

    e.g. 20260820-0043_gtfs_vor_2026.zip        -> vor
         20260819-2354_gtfs_flex_vor_2026.zip   -> vor  (flex_ variant)
    """
    m = re.search(r"_gtfs_(?:flex_)?([a-z0-9]+)_2026\.zip$", name, re.IGNORECASE)
    if m:
        return m.group(1).lower()
    return None


def build_records(catalog):
    records = []
    for ds in catalog:
        if not isinstance(ds, dict):
            continue
        versions = ds.get("activeVersions") or []
        if not versions:
            continue
        dsv = (versions[0] or {}).get("dataSetVersion") or {}
        vid = dsv.get("id")
        fobj = dsv.get("file") or {}
        fname = fobj.get("originalName") or ""
        if not vid or not fname:
            continue
        if not GTFS_RE.search(fname):
            continue

        token = token_from_filename(fname)
        meta = VERBUND.get(token, {})
        provider = meta.get("provider") or (ds.get("nameEn") or "MVO GTFS provider")
        name = ds.get("nameEn") or ds.get("nameDe") or fname
        lic = (ds.get("license") or {}).get("nameEn")

        producer_url = FILE_URL_TMPL.format(vid=vid)
        # slug from the filename core (verbund + flex/drt hint) to stay unique
        core = re.sub(r"^\d+-\d+_", "", fname)
        core = re.sub(r"\.zip$", "", core, flags=re.IGNORECASE)
        rec = {
            "id": "{}-{}".format(CC.lower(), slugify(core)),
            "provider": provider,
            "name": name,
            "cc": CC,
            "subdiv": meta.get("subdiv"),
            "city": meta.get("city"),
            "producer_url": producer_url,
            "hosted_url": None,
            "license": lic or "Datenlizenz Mobilitätsverbünde Österreich",
            "bbox": None,
            "status": "active",
            "official": True,
        }
        records.append(rec)
    return records


def wiener_linien_record():
    return {
        "id": "at-wiener-linien-gtfs",
        "provider": "Wiener Linien",
        "name": "Wiener Linien GTFS (Vienna U-Bahn / tram / bus)",
        "cc": CC,
        "subdiv": "Vienna",
        "city": "Vienna",
        "producer_url": "https://www.wienerlinien.at/ogd_realtime/doku/ogd/gtfs/gtfs.zip",
        "hosted_url": None,
        "license": "CC BY (Open Government Data Wien)",
        "bbox": None,
        "status": "active",
        "official": True,
    }


def main():
    existing = load_existing()
    seen = set()
    for r in existing:
        pu = r.get("producer_url")
        if pu:
            seen.add(pu.rstrip("/"))

    candidates = []
    try:
        catalog = fetch_catalog()
        candidates.extend(build_records(catalog))
    except Exception as e:  # network / parse failures should not abort the run
        print("WARN: MVO catalog fetch failed: {}".format(e))
    # Vienna direct no-auth feed (independent of the MVO catalog)
    candidates.append(wiener_linien_record())

    added = 0
    for rec in candidates:
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
