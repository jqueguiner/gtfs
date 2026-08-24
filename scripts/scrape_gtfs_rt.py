#!/usr/bin/env python3
"""GTFS-Realtime ingest. Transitland Atlas registers ~678 GTFS-RT feeds
(vehicle positions / trip updates / service alerts). This adds them as realtime
catalog records so the catalog covers the live dimension, not just static.

Each RT record carries rt_type (vehicle_positions|trip_updates|alerts), the
protobuf endpoint URL, whether it needs auth, and the operator geohash for
placement. Run: python3 scripts/scrape_gtfs_rt.py [/path/to/transitland-atlas]
"""
import json, os, sys, glob, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "feeds_full.json")
ATLAS = sys.argv[1] if len(sys.argv) > 1 else "/tmp/transitland-atlas"
_B32 = "0123456789bcdefghjkmnpqrstuvwxyz"


def gh_decode(gh):
    la, lb, oa, ob = -90.0, 90.0, -180.0, 180.0
    even = True
    for c in gh:
        i = _B32.find(c)
        if i < 0:
            break
        for bit in (16, 8, 4, 2, 1):
            if even:
                m = (oa + ob) / 2
                if i & bit: oa = m
                else: ob = m
            else:
                m = (la + lb) / 2
                if i & bit: la = m
                else: lb = m
            even = not even
    return (la + lb) / 2, (oa + ob) / 2


def main():
    import reverse_geocoder as rg
    feeds = json.load(open(SRC)) if os.path.exists(SRC) else []
    have = {(f.get("producer_url") or "").rstrip("/") for f in feeds}
    have_ids = {f.get("id") for f in feeds}
    op_gh = {}
    rows = []
    for fp in glob.glob(os.path.join(ATLAS, "feeds", "*.json")):
        d = json.load(open(fp))
        for o in d.get("operators", []):
            oid = o.get("onestop_id", "")
            p = oid.split("-")
            gh = p[1] if len(p) >= 3 and re.fullmatch(r"[0-9bcdefghjkmnpqrstuvwxyz]{2,12}", p[1] or "") else ""
            nm = o.get("name")
            for af in o.get("associated_feeds") or []:
                k = af.get("feed_onestop_id") if isinstance(af, dict) else af
                if k and gh:
                    op_gh.setdefault(k, (gh, nm))
        for x in d.get("feeds", []):
            if x.get("spec") != "gtfs-rt":
                continue
            u = x.get("urls") or {}
            for kind, key in (("vehicle_positions", "realtime_vehicle_positions"),
                              ("trip_updates", "realtime_trip_updates"),
                              ("alerts", "realtime_alerts")):
                url = u.get(key)
                if not url or not str(url).startswith("http"):
                    continue
                fid = x.get("id", "")
                gh, nm = op_gh.get(fid, ("", None))
                p = fid.split("-")
                if not gh and len(p) >= 3 and re.fullmatch(r"[0-9bcdefghjkmnpqrstuvwxyz]{2,12}", p[1] or ""):
                    gh = p[1]
                rows.append({"url": url, "kind": kind, "id": fid, "gh": gh,
                             "provider": nm or (p[-1] if p else fid).replace("~", " "),
                             "auth": bool(x.get("authorization"))})
    pts = [gh_decode(r["gh"]) if r["gh"] else (0.0, 0.0) for r in rows]
    geo = rg.search(pts) if pts else []
    added = 0
    for r, g in zip(rows, geo):
        if r["url"].rstrip("/") in have:
            continue
        have.add(r["url"].rstrip("/"))
        fid = f"rt-{r['kind'][:2]}-{r['id']}"[:60]
        n = 2
        while fid in have_ids:
            fid = f"rt-{r['kind'][:2]}-{r['id']}-{n}"[:60]; n += 1
        have_ids.add(fid)
        feeds.append({"id": fid, "provider": r["provider"],
                      "name": f"{r['provider']} — GTFS-RT {r['kind']}",
                      "cc": g["cc"] if r["gh"] else None,
                      "subdiv": g.get("admin1") if r["gh"] else None,
                      "city": g["name"] if r["gh"] else None,
                      "producer_url": r["url"], "hosted_url": None, "license": None,
                      "bbox": None, "status": "active", "official": False,
                      "source": "gtfs-rt", "realtime": True, "rt_type": r["kind"],
                      "needs_auth": r["auth"]})
        added += 1
    json.dump(feeds, open(SRC, "w"), ensure_ascii=False)
    print(f"gtfs-rt: {len(rows)} RT endpoints, +{added} new")


if __name__ == "__main__":
    main()
