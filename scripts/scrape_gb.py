#!/usr/bin/env python3
"""United Kingdom — BODS (Bus Open Data Service, data.bus-data.dft.gov.uk).
The DfT-mandated national access point: every GB bus operator must publish here.
The `/timetable/download/gtfs-file/all/` endpoint is the whole-country GTFS
(no key). We register the national + regional feeds and split the national feed
by agency.txt so each operator is its own catalog record (filter by agency_id).

Fills the GB gap (transitland only had a handful). Rail (ATOC) is separate.
Appends to data/feeds_full.json (merge + dedup).
"""
import json, os, io, csv, zipfile, hashlib, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "feeds_full.json")
BASE = "https://data.bus-data.dft.gov.uk/timetable/download/gtfs-file"

REGIONS = [
    ("all", "GB — all bus operators (national)", None),
    ("england", "England bus", "England"),
    ("scotland", "Scotland bus", "Scotland"),
    ("wales", "Wales bus", "Wales"),
    ("london", "London bus", "London"),
    ("north_east", "North East England bus", "North East"),
    ("north_west", "North West England bus", "North West"),
    ("yorkshire", "Yorkshire bus", "Yorkshire"),
    ("east_midlands", "East Midlands bus", "East Midlands"),
    ("west_midlands", "West Midlands bus", "West Midlands"),
    ("east_anglia", "East Anglia bus", "East Anglia"),
    ("south_east", "South East England bus", "South East"),
    ("south_west", "South West England bus", "South West"),
]


def fetch_agencies(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "gtfs-catalog/1.0"})
        raw = urllib.request.urlopen(req, timeout=180).read()
        z = zipfile.ZipFile(io.BytesIO(raw))
        name = next((n for n in z.namelist() if n.endswith("agency.txt")), None)
        if not name:
            return []
        with z.open(name) as fh:
            return sorted({r.get("agency_name", "").strip()
                           for r in csv.DictReader(io.TextIOWrapper(fh, "utf-8-sig"))
                           if r.get("agency_name")})
    except Exception as e:
        print("  agency split skipped:", e)
        return []


def main():
    feeds = json.load(open(SRC)) if os.path.exists(SRC) else []
    have = {(f.get("producer_url") or "").rstrip("/") for f in feeds}
    have_ids = {f.get("id") for f in feeds}
    added = 0

    for slug, name, subdiv in REGIONS:
        url = f"{BASE}/{slug}/"
        if url.rstrip("/") in have:
            continue
        have.add(url.rstrip("/"))
        feeds.append({"id": f"gb-bods-{slug}", "provider": name, "name": f"{name} (BODS)",
                      "cc": "GB", "subdiv": subdiv, "city": subdiv, "producer_url": url,
                      "hosted_url": None, "license": "OGL-UK-3.0", "bbox": None,
                      "status": "active", "official": True, "source": "bods"})
        added += 1

    # split the national feed by operator
    agencies = fetch_agencies(f"{BASE}/all/")
    national = f"{BASE}/all/"
    for ag in agencies:
        aid = "gb-op-" + hashlib.md5(ag.encode("utf-8")).hexdigest()[:10]
        if aid in have_ids:
            continue
        have_ids.add(aid)
        feeds.append({"id": aid, "provider": ag, "name": f"{ag} (via BODS national feed)",
                      "cc": "GB", "subdiv": None, "city": None, "producer_url": national,
                      "hosted_url": None, "license": "OGL-UK-3.0", "bbox": None,
                      "status": "active", "official": True, "source": "bods#agency"})
        added += 1
    json.dump(feeds, open(SRC, "w"), ensure_ascii=False)
    print(f"BODS: +{added} GB feeds ({len(agencies)} operators in national feed)")


if __name__ == "__main__":
    main()
