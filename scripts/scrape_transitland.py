#!/usr/bin/env python3
"""Transitland Atlas scraper — the widest OPEN feed registry (Interline).
github.com/transitland/transitland-atlas, no API key. ~4000 static GTFS feeds,
a superset of the Mobility Database in many regions.

Each feed id is `f-<geohash>-name`; we decode the geohash to lat/lon and
reverse-geocode (offline) to country + city, then append records to
data/feeds_full.json in the repo schema. Dedup by producer_url.

Deps: reverse_geocoder (pip install --break-system-packages reverse_geocoder).
Run: python3 scripts/scrape_transitland.py [/path/to/transitland-atlas]
"""
import json, os, sys, glob, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "feeds_full.json")
ATLAS = sys.argv[1] if len(sys.argv) > 1 else "/tmp/transitland-atlas"

_B32 = "0123456789bcdefghjkmnpqrstuvwxyz"

ISO2 = set((
    "US CA MX BR AR CL CO PE UY EC BO PY VE GB IE FR DE NL BE LU CH AT IT ES PT "
    "SE NO DK FI IS PL CZ SK SI HR HU RO BG GR EE LT LV RS BA MK ME AL UA MD "
    "AU NZ JP KR TW SG MY ID PH IN TH VN HK CN LK BD PK NP "
    "ZA KE NG MA EG TN DZ GH ET IL AE SA TR QA"
).split())


def geohash_decode(gh):
    lat_lo, lat_hi, lon_lo, lon_hi = -90.0, 90.0, -180.0, 180.0
    even = True
    for c in gh:
        idx = _B32.find(c)
        if idx < 0:
            break
        for bit in (16, 8, 4, 2, 1):
            if even:
                mid = (lon_lo + lon_hi) / 2
                if idx & bit: lon_lo = mid
                else: lon_hi = mid
            else:
                mid = (lat_lo + lat_hi) / 2
                if idx & bit: lat_lo = mid
                else: lat_hi = mid
            even = not even
    return (lat_lo + lat_hi) / 2, (lon_lo + lon_hi) / 2


def humanize(s):
    return re.sub(r"[-_]+", " ", s).strip().title()


def main():
    if not os.path.isdir(os.path.join(ATLAS, "feeds")):
        sys.exit(f"atlas not found at {ATLAS} (git clone --depth 1 https://github.com/transitland/transitland-atlas)")

    def valid_gh(g):
        return bool(g) and bool(re.fullmatch(r"[0-9bcdefghjkmnpqrstuvwxyz]{2,12}", g))

    feeds, op_by_feed, opgh_by_feed = [], {}, {}
    for fp in glob.glob(os.path.join(ATLAS, "feeds", "*.json")):
        d = json.load(open(fp))
        for o in d.get("operators", []):
            nm = o.get("name")
            oid = o.get("onestop_id", "")
            op = oid.split("-")
            ogh = op[1] if len(op) >= 3 and op[0] == "o" and valid_gh(op[1]) else ""
            for fid in (o.get("associated_feeds") or []):
                key = fid.get("feed_onestop_id") if isinstance(fid, dict) else fid
                if not key:
                    continue
                if nm:
                    op_by_feed.setdefault(key, nm)
                if ogh:
                    opgh_by_feed.setdefault(key, ogh)
        for x in d.get("feeds", []):
            if x.get("spec") != "gtfs":
                continue
            url = (x.get("urls") or {}).get("static_current")
            if not url or not str(url).startswith("http"):
                continue
            fid = x.get("id", "")
            parts = fid.split("-")
            gh = parts[1] if len(parts) >= 3 and parts[0] == "f" and valid_gh(parts[1]) else ""
            if not gh:
                gh = opgh_by_feed.get(fid, "")            # operator's geohash
            cc_tail = ""
            if not gh:                                    # last resort: trailing ISO2 in the id
                toks = [t for t in re.split(r"[-~]", fid) if t]
                if len(toks) >= 2 and toks[-1].upper() in ISO2:
                    cc_tail = toks[-1].upper()
            lic = x.get("license") or {}
            feeds.append({
                "id": fid,
                "gh": gh,
                "cc_tail": cc_tail,
                "provider": op_by_feed.get(fid) or humanize(parts[-1] if parts else fid),
                "url": url,
                "license": lic.get("spdx_identifier") or lic.get("url"),
                "redistribution": lic.get("redistribution_allowed"),
            })

    # batch reverse-geocode all geohash centroids -> cc, city
    import reverse_geocoder as rg
    pts = [geohash_decode(f["gh"]) if f["gh"] else (0.0, 0.0) for f in feeds]
    geo = rg.search(pts)

    existing = json.load(open(SRC)) if os.path.exists(SRC) else []
    have = {(r.get("producer_url") or "").rstrip("/") for r in existing}
    added = 0
    for f, g in zip(feeds, geo):
        u = f["url"].rstrip("/")
        if u in have:
            continue
        have.add(u)
        existing.append({
            "id": f["id"],
            "provider": f["provider"],
            "name": f["provider"],
            "cc": (g["cc"] if f["gh"] else None) or f["cc_tail"] or None,
            "subdiv": (g.get("admin1") if f["gh"] else None) or None,
            "city": g["name"] if f["gh"] else None,
            "producer_url": f["url"],
            "hosted_url": None,
            "license": f["license"],
            "bbox": None,
            "status": "active",
            "official": False,
            "source": "transitland-atlas",
        })
        added += 1
    json.dump(existing, open(SRC, "w"), ensure_ascii=False)
    print(f"transitland-atlas: {len(feeds)} gtfs feeds, +{added} new -> {len(existing)} total. Run build_repo.py.")


if __name__ == "__main__":
    main()
