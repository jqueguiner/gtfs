#!/usr/bin/env python3
"""Place feeds that have no country (cc == null) by downloading the GTFS and
reading a stop's lat/lon, then reverse-geocoding (offline) to country + city.
Authoritative fallback when the feed id carries no geohash/ISO2.

Patches data/feeds_full.json in place. Bounded: per-feed timeout + size cap,
concurrent, skips failures. Run: python3 scripts/resolve_unplaced.py [max_feeds]
"""
import json, os, sys, io, csv, zipfile, urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "feeds_full.json")
MAXBYTES = 80 * 1024 * 1024
TIMEOUT = 40


def one_latlon(url):
    req = urllib.request.Request(url, headers={"User-Agent": "gtfs-catalog/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        cl = r.headers.get("Content-Length")
        if cl and int(cl) > MAXBYTES:
            return None
        raw = r.read(MAXBYTES)
    z = zipfile.ZipFile(io.BytesIO(raw))
    name = next((n for n in z.namelist() if n.endswith("stops.txt")), None)
    if not name:
        return None
    with z.open(name) as fh:
        rdr = csv.DictReader(io.TextIOWrapper(fh, "utf-8-sig"))
        for row in rdr:
            try:
                lat = float(row.get("stop_lat") or "")
                lon = float(row.get("stop_lon") or "")
            except ValueError:
                continue
            if lat or lon:
                return lat, lon
    return None


def main():
    feeds = json.load(open(SRC))
    todo = [(i, f) for i, f in enumerate(feeds)
            if not f.get("cc") and (f.get("producer_url") or f.get("hosted_url"))]
    if len(sys.argv) > 1:
        todo = todo[:int(sys.argv[1])]
    print(f"resolving {len(todo)} unplaced feeds…", flush=True)

    def work(item):
        i, f = item
        try:
            ll = one_latlon(f.get("producer_url") or f["hosted_url"])
            return (i, ll)
        except Exception:
            return (i, None)

    results = []
    with ThreadPoolExecutor(max_workers=16) as ex:
        for n, res in enumerate(ex.map(work, todo), 1):
            results.append(res)
            if n % 100 == 0:
                print(f"  {n}/{len(todo)} fetched", flush=True)

    pts = [(ll[0], ll[1]) for _, ll in results if ll]
    idxs = [i for (i, ll) in results if ll]
    placed = 0
    if pts:
        import reverse_geocoder as rg
        geo = rg.search(pts)
        for i, g in zip(idxs, geo):
            feeds[i]["cc"] = g["cc"]
            feeds[i]["city"] = g["name"]
            feeds[i]["subdiv"] = g.get("admin1") or None
            placed += 1
    json.dump(feeds, open(SRC, "w"), ensure_ascii=False)
    print(f"placed {placed}/{len(todo)} (rest unreachable/no-stops). Run build_repo.py.", flush=True)


if __name__ == "__main__":
    main()
