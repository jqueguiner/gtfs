#!/usr/bin/env python3
"""City-coverage booster. National/aggregate GTFS feeds (one zip serving many
towns) are recorded as a single 'national' catalog entry, so they don't count
toward distinct-city coverage even though they serve hundreds of cities.

This downloads such a feed, reads stops.txt, reverse-geocodes all stops (offline
reverse_geocoder), and emits ONE catalog record per distinct city the feed
serves (producer_url = the national feed, tagged with the city). A national feed
covering 500 towns becomes 500 city entries -> real city coverage.

Extend BIG with (cc, url, provider). Idempotent (dedup by cc+city+url).
Run: python3 scripts/expand_cities.py
"""
import json, os, io, csv, zipfile, ssl, urllib.request
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "feeds_full.json")
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

# big multi-city national/aggregate feeds to expand into per-city records
BIG = [
    ("CZ", "https://www.spojenka.cz/jrdata/jizdnirady-gtfs.zip", "CIS JR (CZ national)"),
    ("CH", "https://gtfs.geops.ch/dl/gtfs_complete.zip", "opentransportdata.swiss"),
    ("NL", "https://gtfs.ovapi.nl/nl/gtfs-nl.zip", "OVapi/NDOV"),
    ("DK", "https://www.rejseplanen.info/labs/GTFS.zip", "Rejseplanen"),
    ("LU", "https://download.data.public.lu/resources/horaires-et-arrets-des-transport-publics-gtfs/20260821-055311/gtfs-20260819-20261212.zip", "mobiliteit.lu"),
    ("GB", "https://data.bus-data.dft.gov.uk/timetable/download/gtfs-file/all/", "BODS"),
    ("DE", "https://download.gtfs.de/germany/free/latest.zip", "gtfs.de"),
    ("FR", "https://eu.ftp.opendatasoft.com/sncf/gtfs/export-ter-gtfs-last.zip", "SNCF TER"),
]
MAX_STOPS = 200000


def stops_of(url):
    req = urllib.request.Request(url, headers={"User-Agent": "gtfs/1.0"})
    raw = urllib.request.urlopen(req, timeout=300, context=_CTX).read()
    z = zipfile.ZipFile(io.BytesIO(raw))
    name = next((n for n in z.namelist() if n.endswith("stops.txt")), None)
    if not name:
        return []
    pts = []
    with z.open(name) as fh:
        for i, r in enumerate(csv.DictReader(io.TextIOWrapper(fh, "utf-8-sig"))):
            if i > MAX_STOPS:
                break
            try:
                lat = float(r.get("stop_lat") or "")
                lon = float(r.get("stop_lon") or "")
            except ValueError:
                continue
            if lat or lon:
                pts.append((lat, lon))
    return pts


def main():
    import reverse_geocoder as rg
    feeds = json.load(open(SRC)) if os.path.exists(SRC) else []
    have_ids = {f.get("id") for f in feeds}
    total = 0
    for cc, url, prov in BIG:
        try:
            pts = stops_of(url)
        except Exception as e:
            print(f"{cc}: fetch failed {str(e)[:40]}")
            continue
        if not pts:
            print(f"{cc}: no stops"); continue
        geo = rg.search(pts)
        # count cities WITHIN this feed's own country only
        cities = defaultdict(int)
        for g in geo:
            if g["cc"] == cc:
                cities[(g["name"], g.get("admin1"))] += 1
        n = 0
        for (city, subdiv), cnt in cities.items():
            if cnt < 2:      # skip a single stray stop
                continue
            import hashlib
            fid = f"{cc.lower()}-city-" + hashlib.md5(f"{city}|{url}".encode()).hexdigest()[:10]
            if fid in have_ids:
                continue
            have_ids.add(fid)
            feeds.append({"id": fid, "provider": f"{prov} — {city}", "name": f"{city} transit ({prov})",
                          "cc": cc, "subdiv": subdiv, "city": city, "producer_url": url,
                          "hosted_url": None, "license": None, "bbox": None,
                          "status": "active", "official": True, "source": "national#city"})
            n += 1; total += 1
        print(f"{cc}: {len(pts)} stops -> {len(cities)} cities, +{n} records")
    json.dump(feeds, open(SRC, "w"), ensure_ascii=False)
    print(f"expand_cities: +{total} per-city records")


if __name__ == "__main__":
    main()
