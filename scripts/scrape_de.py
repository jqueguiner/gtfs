#!/usr/bin/env python3
"""Germany (DE) — gtfs.de. The German NAP (DELFI/Mobilithek) is login-gated;
gtfs.de regenerates the full national GTFS from DELFI daily and serves it at
stable no-login URLs (https://gtfs.de/en/feeds/). The 'germany/free' feed is the
whole-country combined GTFS — every German operator merged into one feed — plus
three mode-split feeds. All free, no key.

For richer per-agency coverage we also split the combined feed by agency.txt:
each agency becomes its own catalog record (same producer_url — the combined zip
— which every GTFS-consumer can load and filter by agency_id).

Appends to data/feeds_full.json. Run: python3 scripts/scrape_de.py
"""
import json, os, io, csv, zipfile, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "feeds_full.json")
BASE = "https://download.gtfs.de/germany"

FEEDS = [
    ("free", "gtfs.de — Germany (all operators, combined)", "germany-all"),
    ("fv_free", "gtfs.de — Germany long-distance rail (FV)", "germany-fv"),
    ("rv_free", "gtfs.de — Germany regional rail (RV)", "germany-rv"),
    ("nv_free", "gtfs.de — Germany local/urban transit (NV)", "germany-nv"),
]


def fetch_agencies(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "gtfs-catalog/1.0"})
        raw = urllib.request.urlopen(req, timeout=120).read()
        z = zipfile.ZipFile(io.BytesIO(raw))
        name = next((n for n in z.namelist() if n.endswith("agency.txt")), None)
        if not name:
            return []
        with z.open(name) as fh:
            return [r.get("agency_name", "").strip()
                    for r in csv.DictReader(io.TextIOWrapper(fh, "utf-8-sig"))
                    if r.get("agency_name")]
    except Exception as e:
        print("  agency split skipped:", e)
        return []


def main():
    feeds = json.load(open(SRC)) if os.path.exists(SRC) else []
    have = {(f.get("producer_url") or "").rstrip("/") for f in feeds}
    have_ids = {f.get("id") for f in feeds}
    added = 0

    # 1) the 4 national gtfs.de free feeds
    for slug, name, fid in FEEDS:
        url = f"{BASE}/{slug}/latest.zip"
        if url.rstrip("/") in have:
            continue
        have.add(url.rstrip("/"))
        feeds.append({"id": f"de-{fid}", "provider": name, "name": name, "cc": "DE",
                      "subdiv": None, "city": None, "producer_url": url, "hosted_url": None,
                      "license": "CC-BY-4.0 (gtfs.de / DELFI)", "bbox": None,
                      "status": "active", "official": True, "source": "gtfs.de"})
        added += 1

    # 2) per-agency records from the combined feed (all German operators)
    agencies = fetch_agencies(f"{BASE}/free/latest.zip")
    combined = f"{BASE}/free/latest.zip"
    seen_ag = set()
    for ag in agencies:
        import hashlib
        aid = "de-ag-" + hashlib.md5(ag.encode("utf-8")).hexdigest()[:10]
        if aid in have_ids or aid in seen_ag:
            continue
        seen_ag.add(aid)
        feeds.append({"id": aid, "provider": ag, "name": f"{ag} (via gtfs.de national feed)",
                      "cc": "DE", "subdiv": None, "city": None, "producer_url": combined,
                      "hosted_url": None, "license": "CC-BY-4.0 (gtfs.de / DELFI)", "bbox": None,
                      "status": "active", "official": True, "source": "gtfs.de#agency"})
        added += 1
    json.dump(feeds, open(SRC, "w"), ensure_ascii=False)
    print(f"gtfs.de: +{added} DE feeds ({len(agencies)} agencies in combined feed). Run build_repo.py.")


if __name__ == "__main__":
    main()
