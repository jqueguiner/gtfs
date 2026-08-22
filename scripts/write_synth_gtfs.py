#!/usr/bin/env python3
"""Write LLM-synthesized GTFS feeds (from gtfs-llm-normalize workflow) into the
repo as real, git-tracked GTFS .txt tables, plus a catalog record.

Input: a JSON array of GTFS objects (agency/stops/routes/trips/stop_times/
calendar + operator/cc/city/confidence). Path via argv[1] or /tmp/synth_gtfs.json.

Each feed -> <CC>/<city-slug>/<operator-slug>/gtfs/*.txt  (loose GTFS, tracked)
         -> data/feeds_full.json record  (source=llm-normalized, confidence)
"""
import json, os, re, sys, csv, io, unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "feeds_full.json")
IN = sys.argv[1] if len(sys.argv) > 1 else "/tmp/synth_gtfs.json"

FILES = {
    "agency": ["agency_id", "agency_name", "agency_url", "agency_timezone"],
    "stops": ["stop_id", "stop_name", "stop_lat", "stop_lon"],
    "routes": ["route_id", "route_short_name", "route_long_name", "route_type"],
    "trips": ["route_id", "service_id", "trip_id", "trip_headsign"],
    "stop_times": ["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"],
    "calendar": ["service_id", "monday", "tuesday", "wednesday", "thursday",
                 "friday", "saturday", "sunday", "start_date", "end_date"],
}


def slug(s, fb="x"):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s or fb


def write_csv(path, cols, rows):
    rows = [rows] if isinstance(rows, dict) else (rows or [])
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cols)
    for r in rows:
        w.writerow([r.get(c, "") if isinstance(r, dict) else "" for c in cols])
    open(path, "w", encoding="utf-8").write(buf.getvalue())


def main():
    data = json.load(open(IN))
    feeds = data.get("built", data) if isinstance(data, dict) else data
    catalog = json.load(open(SRC)) if os.path.exists(SRC) else []
    have_ids = {f.get("id") for f in catalog}
    written = 0
    for g in feeds:
        if not g or (g.get("confidence") or 0) < 0.4:
            continue
        if len(g.get("stops") or []) < 3 or len(g.get("stop_times") or []) < 3:
            continue
        cc = (g.get("cc") or "XX").upper()
        city = g.get("city") or "national"
        op = g.get("operator") or (g.get("agency") or {}).get("agency_name") or "operator"
        # store under top-level synthesized/ (build_repo wipes the <CC>/ country tree)
        d = os.path.join(ROOT, "synthesized", cc, slug(city)[:40], slug(op)[:48], "gtfs")
        os.makedirs(d, exist_ok=True)
        ag = g.get("agency") or {}
        ag.setdefault("agency_id", slug(op))
        write_csv(os.path.join(d, "agency.txt"), FILES["agency"], ag)
        for name in ("stops", "routes", "trips", "stop_times", "calendar"):
            write_csv(os.path.join(d, name + ".txt"), FILES[name], g.get(name))
        meta = {"operator": op, "city": city, "cc": cc, "confidence": g.get("confidence"),
                "counts": {k: len(g.get(k) or []) for k in ("stops", "routes", "trips", "stop_times")},
                "notes": g.get("notes"), "source": "llm-normalized"}
        json.dump(meta, open(os.path.join(os.path.dirname(d), "feed.json"), "w"), indent=2, ensure_ascii=False)

        rel = os.path.relpath(d, ROOT)
        fid = f"{cc.lower()}-llm-{slug(op)[:40]}"
        n = 2
        while fid in have_ids:
            fid = f"{cc.lower()}-llm-{slug(op)[:40]}-{n}"; n += 1
        have_ids.add(fid)
        catalog.append({
            "id": fid, "provider": op, "name": f"{op} ({city}) — LLM-synthesized GTFS",
            "cc": cc, "subdiv": None, "city": city,
            "producer_url": f"https://raw.githubusercontent.com/jqueguiner/gtfs/main/{rel}/",
            "hosted_url": None, "license": None, "bbox": None, "status": "active",
            "official": False, "source": "llm-normalized", "confidence": g.get("confidence"),
        })
        written += 1
    json.dump(catalog, open(SRC, "w"), ensure_ascii=False)
    print(f"wrote {written} LLM-synthesized GTFS feeds into the repo + catalog")


if __name__ == "__main__":
    main()
