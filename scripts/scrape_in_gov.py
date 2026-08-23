#!/usr/bin/env python3
"""India — government/agency GTFS feeds published directly (no national NAP).
Indian states/cities each publish their own GTFS; this registers the verified
direct-download endpoints (extend as more are found). TLS on some gov sites is
misconfigured, so URLs are recorded as-is; consumers fetch with a tolerant
client. Metros are additionally covered via LLM-synthesis (synthesized/).

Appends to data/feeds_full.json (merge + dedup).
"""
import json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "feeds_full.json")

# (id, provider, city, subdiv, url, license) — each VERIFIED to contain stops.txt
FEEDS = [
    ("in-goa-ktcl", "Kadamba Transport Corp (KTCL) + Goa buses", "Goa", "Goa",
     "https://goatransport.gov.in/download_Forms/gtfs.zip", "GoI-OGDL"),
    ("in-kochi-kmrl", "Kochi Metro Rail Ltd (KMRL)", "Kochi", "Kerala",
     "https://kochimetro.org/opendata/KMRLOpenData.zip", None),
    ("in-kochi-transport", "KochiTransport (Jungle Bus / OSM community)", "Kochi", "Kerala",
     "https://jungle-bus.github.io/KochiTransport/KochiTransport.zip", "ODbL-1.0"),
    # Delhi OTD — official open transit data, no key (per-file form POST, no login).
    # GTFS served as individual .txt via a usage form; producer_url = the portal page.
    ("in-delhi-otd-bus", "Delhi OTD — DTC + DIMTS cluster buses", "Delhi", "Delhi",
     "https://otd.delhi.gov.in/data/static/", "GoI-OGDL"),
    ("in-delhi-otd-dmrc", "Delhi OTD — DMRC (Delhi Metro)", "Delhi", "Delhi",
     "https://otd.delhi.gov.in/data/staticDMRC/", "GoI-OGDL"),
]


def main():
    feeds = json.load(open(SRC)) if os.path.exists(SRC) else []
    have = {(f.get("producer_url") or "").rstrip("/") for f in feeds}
    have_ids = {f.get("id") for f in feeds}
    added = 0
    for fid, prov, city, subdiv, url, lic in FEEDS:
        if url.rstrip("/") in have or fid in have_ids:
            continue
        have.add(url.rstrip("/"))
        feeds.append({"id": fid, "provider": prov, "name": f"{prov} — {city}",
                      "cc": "IN", "subdiv": subdiv, "city": city, "producer_url": url,
                      "hosted_url": None, "license": lic, "bbox": None,
                      "status": "active", "official": True, "source": "in-gov"})
        added += 1
    json.dump(feeds, open(SRC, "w"), ensure_ascii=False)
    print(f"in-gov: +{added} IN feeds")


if __name__ == "__main__":
    main()
