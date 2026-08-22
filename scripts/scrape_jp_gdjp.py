#!/usr/bin/env python3
"""Japan — gtfs-data.jp national repository (api.gtfs-data.jp/v2/feeds).
~600 municipal/operator GTFS feeds, each with a canonical current-download URL,
prefecture, and license. Fills the Japanese small-town long tail.

Appends to data/feeds_full.json (merge + dedup by producer_url).
"""
import json, os, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "feeds_full.json")
API = "https://api.gtfs-data.jp/v2/feeds"

PREF = {1: "Hokkaido", 2: "Aomori", 3: "Iwate", 4: "Miyagi", 5: "Akita", 6: "Yamagata",
        7: "Fukushima", 8: "Ibaraki", 9: "Tochigi", 10: "Gunma", 11: "Saitama", 12: "Chiba",
        13: "Tokyo", 14: "Kanagawa", 15: "Niigata", 16: "Toyama", 17: "Ishikawa", 18: "Fukui",
        19: "Yamanashi", 20: "Nagano", 21: "Gifu", 22: "Shizuoka", 23: "Aichi", 24: "Mie",
        25: "Shiga", 26: "Kyoto", 27: "Osaka", 28: "Hyogo", 29: "Nara", 30: "Wakayama",
        31: "Tottori", 32: "Shimane", 33: "Okayama", 34: "Hiroshima", 35: "Yamaguchi",
        36: "Tokushima", 37: "Kagawa", 38: "Ehime", 39: "Kochi", 40: "Fukuoka", 41: "Saga",
        42: "Nagasaki", 43: "Kumamoto", 44: "Oita", 45: "Miyazaki", 46: "Kagoshima", 47: "Okinawa"}


def main():
    req = urllib.request.Request(API, headers={"User-Agent": "gtfs-catalog/1.0"})
    body = json.load(urllib.request.urlopen(req, timeout=90)).get("body") or []
    feeds = json.load(open(SRC)) if os.path.exists(SRC) else []
    have = {(f.get("producer_url") or "").rstrip("/") for f in feeds}
    have_ids = {f.get("id") for f in feeds}
    added = 0
    for f in body:
        if f.get("feed_is_discontinued"):
            continue
        url = f.get("feed_src_gtfs_current_url")
        if not url or url.rstrip("/") in have:
            continue
        have.add(url.rstrip("/"))
        pref = PREF.get(f.get("feed_pref_id") or f.get("organization_pref_id"))
        fid = f"jp-gdjp-{f.get('organization_id')}-{f.get('feed_id')}"
        if fid in have_ids:
            continue
        have_ids.add(fid)
        feeds.append({
            "id": fid, "provider": f.get("organization_name"),
            "name": f.get("feed_name") or f.get("organization_name"),
            "cc": "JP", "subdiv": pref, "city": pref,
            "producer_url": url, "hosted_url": None,
            "license": f.get("feed_license"), "bbox": None,
            "status": "active", "official": True, "source": "gtfs-data.jp",
        })
        added += 1
    json.dump(feeds, open(SRC, "w"), ensure_ascii=False)
    print(f"gtfs-data.jp: {len(body)} feeds, +{added} new -> {len(feeds)} total")


if __name__ == "__main__":
    main()
