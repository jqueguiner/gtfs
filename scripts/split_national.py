#!/usr/bin/env python3
"""Agency-split national NAP GTFS feeds into per-operator catalog records.
A national combined feed (one zip, dozens of operators) becomes many records,
each filterable by agency_id. Deterministic (no LLM) — the cron reruns this to
keep per-country coverage maintained + growing as new operators appear.

Extend NATIONAL with any (cc, url, id_prefix, provider) national feed.
Appends to data/feeds_full.json (merge + dedup).
"""
import json, os, io, csv, zipfile, hashlib, ssl, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "feeds_full.json")
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

# (cc, national feed url, id-prefix, human source label)
NATIONAL = [
    ("NL", "https://gtfs.ovapi.nl/nl/gtfs-nl.zip", "nl-op", "OVapi/NDOV"),
    ("CH", "https://gtfs.geops.ch/dl/gtfs_complete.zip", "ch-op", "opentransportdata.swiss"),
    ("DK", "https://www.rejseplanen.info/labs/GTFS.zip", "dk-op", "Rejseplanen"),
    ("CZ", "https://www.spojenka.cz/jrdata/jizdnirady-gtfs.zip", "cz-cis", "CIS JR"),
    ("LU", "https://download.data.public.lu/resources/horaires-et-arrets-des-transport-publics-gtfs/20260821-055311/gtfs-20260819-20261212.zip", "lu-op", "mobiliteit.lu"),
]


def main():
    feeds = json.load(open(SRC)) if os.path.exists(SRC) else []
    have = {(f.get("producer_url") or "").rstrip("/") for f in feeds}
    have_ids = {f.get("id") for f in feeds}
    added = 0
    for cc, url, pfx, label in NATIONAL:
        if url.rstrip("/") not in have:
            feeds.append({"id": f"{cc.lower()}-national", "provider": f"{label} — {cc} national",
                          "name": f"{cc} national GTFS ({label})", "cc": cc, "subdiv": None, "city": None,
                          "producer_url": url, "hosted_url": None, "license": None, "bbox": None,
                          "status": "active", "official": True, "source": "national"})
            have.add(url.rstrip("/")); added += 1
        try:
            raw = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "gtfs/1.0"}),
                                         timeout=240, context=_CTX).read()
            z = zipfile.ZipFile(io.BytesIO(raw))
            nm = next((n for n in z.namelist() if n.endswith("agency.txt")), None)
            ags = []
            if nm:
                with z.open(nm) as fh:
                    ags = sorted({r.get("agency_name", "").strip()
                                  for r in csv.DictReader(io.TextIOWrapper(fh, "utf-8-sig"))
                                  if r.get("agency_name")})
            n = 0
            for ag in ags[:600]:
                aid = pfx + "-" + hashlib.md5(ag.encode("utf-8")).hexdigest()[:10]
                if aid in have_ids:
                    continue
                have_ids.add(aid)
                feeds.append({"id": aid, "provider": ag, "name": f"{ag} (via {cc} national feed)",
                              "cc": cc, "subdiv": None, "city": None, "producer_url": url,
                              "hosted_url": None, "license": None, "bbox": None,
                              "status": "active", "official": True, "source": f"{cc.lower()}-nap#agency"})
                n += 1; added += 1
            print(f"{cc}: {len(ags)} agencies, +{n}")
        except Exception as e:
            print(f"{cc}: split failed: {str(e)[:50]}")
    json.dump(feeds, open(SRC, "w"), ensure_ascii=False)
    print(f"split_national: +{added} total")


if __name__ == "__main__":
    main()
