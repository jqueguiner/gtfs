#!/usr/bin/env python3
"""FR priority scraper: transport.data.gouv.fr is the French national GTFS
aggregator (every AOM / operator is legally required to publish there). This
pulls its open API and merges any GTFS resource not already in the MDB dump
into data/feeds_full.json (dedup by producer_url), so France stays exhaustive.

No key. Run: python3 scripts/scrape_france.py
"""
import json, os, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "https://transport.data.gouv.fr/api/datasets"
SRC = os.path.join(ROOT, "data", "feeds_full.json")


def get(url):
    r = urllib.request.Request(url, headers={"User-Agent": "gtfs-catalog/1.0"})
    return json.load(urllib.request.urlopen(r, timeout=120))


def main():
    feeds = json.load(open(SRC)) if os.path.exists(SRC) else []
    have = {(f.get("producer_url") or "").rstrip("/") for f in feeds}
    added = 0
    for d in get(API):
        areas = d.get("covered_area") or []          # [{type, nom, insee}]
        areas = areas if isinstance(areas, list) else [areas]
        by = {a.get("type"): a.get("nom") for a in areas if isinstance(a, dict)}
        city = by.get("commune") or by.get("aom") or by.get("epci")
        region = by.get("region")
        publisher = (d.get("publisher") or {})
        provider = publisher.get("name") if isinstance(publisher, dict) else None
        for res in d.get("resources", []):
            if res.get("format") != "GTFS":
                continue
            url = res.get("original_url") or res.get("url")
            if not url or url.rstrip("/") in have:
                continue
            have.add(url.rstrip("/"))
            feeds.append({
                "id": f"tdg-{res.get('id')}",
                "provider": provider or d.get("title"),
                "name": d.get("title"),
                "cc": "FR",
                "subdiv": region,
                "city": city,
                "producer_url": url,
                "hosted_url": None,
                "license": d.get("licence"),
                "bbox": None,
                "status": "active",
                "official": True,
            })
            added += 1
    json.dump(feeds, open(SRC, "w"), ensure_ascii=False)
    print(f"transport.data.gouv.fr: +{added} new FR feeds -> {len(feeds)} total. Run build_repo.py next.")


if __name__ == "__main__":
    main()
