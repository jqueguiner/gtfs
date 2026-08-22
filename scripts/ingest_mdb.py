#!/usr/bin/env python3
"""Pull the Mobility Database catalog -> data/feeds_full.json (source for
build_repo.py). Auth: set MDB_REFRESH_TOKEN env (get one at
https://mobilitydatabase.org, account -> API refresh token).

Uses source_info.producer_url (the agency's own public feed) rather than the
GCS-hosted mirror, which needs signed auth. Run: MDB_REFRESH_TOKEN=... python3 scripts/ingest_mdb.py
"""
import json, os, sys, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOK = "https://api.mobilitydatabase.org/v1/tokens"
API = "https://api.mobilitydatabase.org/v1/gtfs_feeds"


def access_token(refresh):
    body = json.dumps({"refresh_token": refresh}).encode()
    r = urllib.request.Request(TOK, data=body, headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=30))["access_token"]


def get(url, at):
    r = urllib.request.Request(url, headers={"Authorization": "Bearer " + at})
    return json.load(urllib.request.urlopen(r, timeout=90))


def main():
    rt = os.environ.get("MDB_REFRESH_TOKEN")
    if not rt:
        sys.exit("set MDB_REFRESH_TOKEN (https://mobilitydatabase.org account page)")
    at = access_token(rt)
    out, off = [], 0
    while True:
        batch = get(f"{API}?limit=100&offset={off}", at)
        if not batch:
            break
        for f in batch:
            si = f.get("source_info") or {}
            loc = f.get("locations") or [{}]
            loc = loc[0] if loc else {}
            bb = f.get("latest_dataset", {}).get("bounding_box") if f.get("latest_dataset") else None
            out.append({
                "id": f["id"],
                "provider": f.get("provider"),
                "name": f.get("feed_name"),
                "cc": loc.get("country_code"),
                "subdiv": loc.get("subdivision_name"),
                "city": loc.get("municipality"),
                "producer_url": si.get("producer_url"),
                "hosted_url": (f.get("latest_dataset") or {}).get("hosted_url"),
                "license": f.get("feed_contact_email") and None or si.get("license_url"),
                "bbox": bb,
                "status": f.get("status") or "active",
                "official": f.get("official", False),
            })
        off += 100
        if len(batch) < 100:
            break
    os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
    json.dump(out, open(os.path.join(ROOT, "data", "feeds_full.json"), "w"), ensure_ascii=False)
    active = [f for f in out if f["status"] not in ("deprecated", "inactive") and (f["producer_url"] or f["hosted_url"])]
    print(f"pulled {len(out)} feeds, {len(active)} active w/ url -> data/feeds_full.json")


if __name__ == "__main__":
    main()
