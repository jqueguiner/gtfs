#!/usr/bin/env python3
"""
Japan (JP) GTFS feed scraper.

Source: GTFS Data Repository (GTFSデータリポジトリ, gtfs-data.jp) -- the de-facto
national bulk source run by the Japan Bus Information Association / APIGDDC.
Japan has no EU-style legally-mandated NAP; gtfs-data.jp is the primary national
access point and is bottom-up (municipal community buses dominate).

  GET https://api.gtfs-data.jp/v2/feeds   (no auth, no API key)

Response JSON: {"code":200,"message":"ok","body":[ ...feed objects... ]}.
~598 feeds / 436 organizations. Each feed object exposes:
  organization_id, organization_name, feed_id, feed_name, feed_pref_id
  (JP prefecture code 1-47), feed_license (mostly 'CC BY 4.0'), feed_license_url,
  last_updated_at, feed_is_discontinued, real_time{trip_update_url,
  vehicle_position_url, alert_url}.

Static GTFS zip: feed_src_gtfs_current_url is almost always null -- DO NOT rely
on it. The canonical, stable download is the repo redirect URL:
  https://api.gtfs-data.jp/v2/organizations/{org}/feeds/{feed}/files/feed.zip
which returns HTTP 302 -> a presigned S3 object; clients follow the redirect to
fetch the zip. We store this stable repo URL as producer_url (it is durable,
unlike the short-lived signed S3 link).

Skips feeds where feed_is_discontinued is true. Appends records to
data/feeds_full.json in the exact repo schema, dedup by producer_url
(rstrip('/')). stdlib only.

The ODPT / Public Transportation Open Data Center (developer.odpt.org) is the
SECONDARY source for Tokyo metro/rail (Tokyo Metro, Toei, JR East, private rail)
but REQUIRES free registration + an API key (consumerKey), so it is intentionally
NOT scraped here.
"""
import json
import os
import re
import urllib.request

CC = "JP"
API_URL = "https://api.gtfs-data.jp/v2/feeds"
# stable canonical download (302 -> presigned S3); durable, so used as producer_url
FEED_ZIP_URL = "https://api.gtfs-data.jp/v2/organizations/{org}/feeds/{feed}/files/feed.zip"
UA = "Mozilla/5.0 (compatible; gtfs-catalog-bot/1.0)"
TIMEOUT = 90

SRC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "feeds_full.json",
)

# JP prefecture code (feed_pref_id) -> romanized prefecture name, for `subdiv`.
# Code 99 is used for "nationwide / unspecified" organizations -> None.
PREFECTURES = {
    1: "Hokkaido", 2: "Aomori", 3: "Iwate", 4: "Miyagi", 5: "Akita",
    6: "Yamagata", 7: "Fukushima", 8: "Ibaraki", 9: "Tochigi", 10: "Gunma",
    11: "Saitama", 12: "Chiba", 13: "Tokyo", 14: "Kanagawa", 15: "Niigata",
    16: "Toyama", 17: "Ishikawa", 18: "Fukui", 19: "Yamanashi", 20: "Nagano",
    21: "Gifu", 22: "Shizuoka", 23: "Aichi", 24: "Mie", 25: "Shiga",
    26: "Kyoto", 27: "Osaka", 28: "Hyogo", 29: "Nara", 30: "Wakayama",
    31: "Tottori", 32: "Shimane", 33: "Okayama", 34: "Hiroshima", 35: "Yamaguchi",
    36: "Tokushima", 37: "Kagawa", 38: "Ehime", 39: "Kochi", 40: "Fukuoka",
    41: "Saga", 42: "Nagasaki", 43: "Kumamoto", 44: "Oita", 45: "Miyazaki",
    46: "Kagoshima", 47: "Okinawa",
}


def slugify(s):
    """ASCII slug; JP feed/org ids are already ascii, but names may not be."""
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def fetch_feeds():
    """GET the aggregator; return the body[] list of feed objects."""
    req = urllib.request.Request(API_URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        data = json.load(resp)
    if data.get("code") != 200:
        raise RuntimeError("unexpected API code: %r" % data.get("code"))
    return data.get("body", []) or []


def build_records(feeds):
    records = []
    for f in feeds:
        if f.get("feed_is_discontinued"):
            continue
        org = (f.get("organization_id") or "").strip()
        fid = (f.get("feed_id") or "").strip()
        if not org or not fid:
            continue

        producer_url = FEED_ZIP_URL.format(org=org, feed=fid)

        org_name = (f.get("organization_name") or org).strip()
        feed_name = (f.get("feed_name") or fid).strip()

        pref_id = f.get("feed_pref_id")
        subdiv = PREFECTURES.get(pref_id) if isinstance(pref_id, int) else None

        lic = f.get("feed_license") or None
        # normalize empty-string licenses to None
        if isinstance(lic, str) and not lic.strip():
            lic = None

        # id slug from the stable org/feed identifiers (already ascii, unique)
        slug = slugify("%s-%s" % (org, fid)) or slugify(org) or slugify(fid)

        records.append({
            "id": "%s-%s" % (CC.lower(), slug),
            "provider": org_name,
            "name": feed_name,
            "cc": CC,
            "subdiv": subdiv,
            "city": None,
            "producer_url": producer_url,
            "hosted_url": None,
            "license": lic,
            "bbox": None,
            "status": "active",
            "official": True,
        })
    return records


def main():
    with open(SRC, "r", encoding="utf-8") as f:
        existing = json.load(f)

    seen = {(e.get("producer_url") or "").rstrip("/") for e in existing}
    seen_ids = {e.get("id") for e in existing}

    try:
        feeds = fetch_feeds()
    except Exception as e:
        print("  ! fetch failed: %s" % e)
        print("+0 new %s feeds" % CC)
        return
    print("fetched %d feeds from gtfs-data.jp" % len(feeds))

    candidates = build_records(feeds)

    new = []
    local_seen = set()
    for rec in candidates:
        key = rec["producer_url"].rstrip("/")
        if key in seen or key in local_seen:
            continue
        local_seen.add(key)
        # ensure unique id
        rid = rec["id"]
        n = 2
        while rid in seen_ids:
            rid = "%s-%d" % (rec["id"], n)
            n += 1
        rec["id"] = rid
        seen_ids.add(rid)
        new.append(rec)

    if new:
        existing.extend(new)
        with open(SRC, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

    print("+%d new %s feeds" % (len(new), CC))


if __name__ == "__main__":
    main()
