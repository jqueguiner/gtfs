#!/usr/bin/env python3
"""Register operator live-map backend realtime endpoints (from rt_web_feeds.json)
into the catalog. These are the JSON/protobuf/SIRI/GeoJSON APIs that operator
websites' live maps call — realtime even where no standard GTFS-RT is published.

Durable/reproducible (unlike a one-off merge): the hourly cron reruns this so the
web-RT feeds survive every rebuild+push cycle. Extend scripts/rt_web_feeds.json.
"""
import json, os, re, unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "feeds_full.json")
DATA = os.path.join(ROOT, "scripts", "rt_web_feeds.json")


def slug(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-") or "x"


def main():
    if not os.path.exists(DATA):
        print("no rt_web_feeds.json"); return
    rows = json.load(open(DATA))
    feeds = json.load(open(SRC)) if os.path.exists(SRC) else []
    have = {(f.get("producer_url") or "").rstrip("/") for f in feeds}
    hid = {f.get("id") for f in feeds}
    added = 0
    for r in rows:
        u = (r.get("url") or "").strip()
        if not u.startswith("http") or u.rstrip("/") in have:
            continue
        cc = (r.get("cc") or "XX").upper()
        if not re.fullmatch(r"[A-Z]{2}", cc):
            continue
        have.add(u.rstrip("/"))
        prov = r.get("provider") or r.get("city") or cc
        fid = f"rtweb-{cc.lower()}-{slug(prov)[:26]}"
        n = 2
        while fid in hid:
            fid = f"rtweb-{cc.lower()}-{slug(prov)[:26]}-{n}"; n += 1
        hid.add(fid)
        feeds.append({"id": fid, "provider": prov,
                      "name": f"{prov} — live {r.get('rt_type', 'positions')}",
                      "cc": cc, "subdiv": r.get("subdiv"), "city": r.get("city"),
                      "producer_url": u, "hosted_url": None, "license": None, "bbox": None,
                      "status": "active", "official": True, "source": "rt-web",
                      "realtime": True, "rt_type": r.get("rt_type"),
                      "rt_format": r.get("rt_format"), "needs_auth": r.get("needs_auth", False)})
        added += 1
    json.dump(feeds, open(SRC, "w"), ensure_ascii=False)
    print(f"rt-web: {len(rows)} endpoints, +{added} new")


if __name__ == "__main__":
    main()
