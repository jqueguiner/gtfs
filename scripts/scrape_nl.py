#!/usr/bin/env python3
"""Netherlands — OVapi/NDOV national GTFS (gtfs.ovapi.nl/nl/gtfs-nl.zip).
The whole-NL feed (NS rail, GVB, RET, HTM, Connexxion, Arriva, Qbuzz, EBS,
Keolis, U-OV...). Split by agency.txt so each operator is its own catalog
record (filter by agency_id). Appends to data/feeds_full.json.
"""
import json, os, io, csv, zipfile, hashlib, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "feeds_full.json")
URL = "https://gtfs.ovapi.nl/nl/gtfs-nl.zip"


def main():
    feeds = json.load(open(SRC)) if os.path.exists(SRC) else []
    have = {(f.get("producer_url") or "").rstrip("/") for f in feeds}
    have_ids = {f.get("id") for f in feeds}
    added = 0
    if URL.rstrip("/") not in have:
        feeds.append({"id": "nl-ovapi-national", "provider": "OVapi — Netherlands national",
                      "name": "Netherlands national GTFS (OVapi/NDOV)", "cc": "NL", "subdiv": None,
                      "city": None, "producer_url": URL, "hosted_url": None, "license": "CC0",
                      "bbox": None, "status": "active", "official": True, "source": "ovapi"})
        have.add(URL.rstrip("/")); added += 1
    try:
        raw = urllib.request.urlopen(urllib.request.Request(URL, headers={"User-Agent": "gtfs/1.0"}), timeout=180).read()
        z = zipfile.ZipFile(io.BytesIO(raw))
        name = next((n for n in z.namelist() if n.endswith("agency.txt")), None)
        agencies = []
        if name:
            with z.open(name) as fh:
                agencies = sorted({r.get("agency_name", "").strip()
                                   for r in csv.DictReader(io.TextIOWrapper(fh, "utf-8-sig"))
                                   if r.get("agency_name")})
        for ag in agencies:
            aid = "nl-op-" + hashlib.md5(ag.encode("utf-8")).hexdigest()[:10]
            if aid in have_ids:
                continue
            have_ids.add(aid)
            feeds.append({"id": aid, "provider": ag, "name": f"{ag} (via NL national feed)",
                          "cc": "NL", "subdiv": None, "city": None, "producer_url": URL,
                          "hosted_url": None, "license": "CC0", "bbox": None,
                          "status": "active", "official": True, "source": "ovapi#agency"})
            added += 1
        print(f"NL OVapi: +{added} ({len(agencies)} operators in national feed)")
    except Exception as e:
        print("NL agency split failed:", e)
    json.dump(feeds, open(SRC, "w"), ensure_ascii=False)


if __name__ == "__main__":
    main()
