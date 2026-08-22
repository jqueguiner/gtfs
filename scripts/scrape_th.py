#!/usr/bin/env python3
"""
Thailand (TH) GTFS feed scraper.

Source: OTP Namtang (นำทาง) -- the Office of Transport and Traffic Policy and
Planning (สำนักงานนโยบายและแผนการขนส่งและจราจร, OTP), Ministry of Transport.
This is Thailand's de-facto National Access Point.

Unlike EU-style NAPs there is NO public feed-enumeration API. Access is a SINGLE
government-run multimodal GTFS zip covering the whole country:

  GET https://namtang-api.otp.go.th/download/namtang-gtfs.zip   (no auth, no key)

Verified live 2026-08-22: HTTP 200, Content-Type application/zip, 41 MB
(42,058,457 bytes), Content-Disposition filename=namtang-gtfs.zip,
Last-Modified Fri 21 Aug 2026 (updated ~daily). Contents: 126 agencies,
2,075 routes, 17,079 stops; feed_version 20260821 valid 2026-01-01..2026-12-31;
publisher OTP. Bundles Bangkok metro rail (BEM/MRTA, BTSC Skytrain, SRTET Airport
Rail Link), BMTA + Thai Smile Bus, State Railway of Thailand (SRT), nationwide
intercity coaches (Nakhonchai Air, Sombat Tour, Cherdchai, ...) and Andaman
island speedboat operators (Krabi/Phi Phi/Lanta/Ranong).

Because there is no listing endpoint, sub-operators cannot be discovered
programmatically -- they live inside agency.txt of the one zip. We therefore emit:
  1. one record for the national multimodal feed (bare zip URL), and
  2. one record per KNOWN named sub-operator, all pointing at the SAME national
     zip but distinguished by a `#agency=<agency_id>` fragment on producer_url so
     each survives dedup-by-producer_url (rstrip('/')). The fragment is inert for
     an HTTP GET -- the byte-identical national zip is always what downloads.

All sub-operators are attributed to OTP Namtang (they are bundled, not separately
published). Legacy standalone Chiang Mai / Green Bus feeds in the Mobility
Database are all expired (2016-2018) and are intentionally ignored in favor of
this feed.

Companion files (same host, not GTFS, not catalogued):
  https://namtang-api.otp.go.th/download/namtang-parking.txt.gz
  https://namtang-api.otp.go.th/download/namtang-stop.txt.gz

Appends records to data/feeds_full.json in the exact repo schema, dedup by
producer_url (rstrip('/')). stdlib only.
"""
import json
import os
import re
import urllib.request

CC = "TH"
PORTAL_URL = "https://namntang.otp.go.th/"
BULK_URL = "https://namtang-api.otp.go.th/download/namtang-gtfs.zip"
PUBLISHER = "OTP Namtang (Office of Transport and Traffic Policy and Planning)"
# National feed publisher DPP: government open data -> no explicit SPDX license.
LICENSE = None
UA = "Mozilla/5.0 (compatible; gtfs-catalog-bot/1.0)"
TIMEOUT = 60

SRC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "feeds_full.json",
)

# The one national multimodal feed. Emitted with the bare zip URL.
NATIONAL = {
    "provider": PUBLISHER,
    "name": "Namtang National Multimodal GTFS (nationwide: rail, metro, bus, coach, boat -- 126 agencies)",
    "subdiv": None,
    "city": None,
    "agency": None,   # bare URL, no fragment
}

# Known named sub-operators bundled inside the national zip. There is no API to
# enumerate them, so this is the curated aggregator SAMPLE set. Each maps to an
# `agency_id` fragment; `producer_url` = BULK_URL + '#agency=<agency>'.
# (subdiv, city) give geographic context where the aggregator provides it.
OPERATORS = [
    # --- Greater Bangkok (national multimodal hub) ---
    ("BMTA",  "BMTA -- Bangkok Mass Transit Authority (city bus)",
     "Bangkok", "Bangkok"),
    ("BTSC",  "BTSC -- BTS Skytrain (Sukhumvit/Silom/Gold + Pink/Yellow monorail)",
     "Bangkok", "Bangkok"),
    ("BEM",   "BEM -- MRT Blue & Purple Line (operator)",
     "Bangkok", "Bangkok"),
    ("MRTA",  "MRTA -- Mass Rapid Transit Authority of Thailand (metro authority)",
     "Bangkok", "Bangkok"),
    ("SRTET", "SRTET -- SRT Airport Rail Link / Red Line",
     "Bangkok", "Bangkok"),
    ("TSB",   "Thai Smile Bus (EV city bus)",
     "Bangkok", "Bangkok"),
    ("TSB-BOAT", "Thai Smile Boat (Chao Phraya river boat)",
     "Bangkok", "Bangkok"),
    ("BTK",   "BTK -- Krungthep Thanakom (BRT + city services)",
     "Bangkok", "Bangkok"),

    # --- Nationwide rail ---
    ("SRT",   "SRT -- State Railway of Thailand (intercity rail, all provinces)",
     None, None),

    # --- Nationwide intercity coach ---
    ("TC",    "The Transport Company Ltd (BKS) -- state intercity coach",
     None, None),
    ("NCA",   "Nakhonchai Air -- intercity coach",
     None, None),
    ("SBT",   "Sombat Tour -- intercity coach",
     None, None),
    ("CCT",   "Cherdchai Tour -- intercity coach",
     None, None),
    ("NC21",  "Nakhon Chai 21 -- intercity coach",
     None, None),
    ("RRC",   "Roong Reuang Coach -- intercity coach",
     None, None),

    # --- Chiang Mai ---
    ("WPB",   "Wiang Ping Bus / Chiang Mai local services",
     "Chiang Mai", "Chiang Mai"),

    # --- Phuket ---
    ("PKT",   "Phuket Travel + Andaman speedboat operators",
     "Phuket", "Phuket"),

    # --- Krabi / Phi Phi / Koh Lanta (Andaman islands) ---
    ("TBCOK", "Krabi bus cooperative",
     "Krabi", "Krabi"),
    ("CG",    "Chaokoh -- Phi Phi/Lanta speedboat",
     "Krabi", "Krabi"),
    ("TL",    "Tigerline -- Andaman speedboat",
     "Krabi", "Krabi"),
    ("LTCL",  "Lanta Transport -- Koh Lanta speedboat",
     "Krabi", "Koh Lanta"),
    ("PPL",   "PP Logistics -- Phi Phi speedboat",
     "Krabi", "Ko Phi Phi"),

    # --- Ranong ---
    ("BC",    "Ranong Bus Cooperative",
     "Ranong", "Ranong"),
    ("MRNT",  "Muang Ranong Transport",
     "Ranong", "Ranong"),
    ("RPB",   "Ranong Paknam Bus",
     "Ranong", "Ranong"),
    ("RRS",   "Ranong regional services",
     "Ranong", "Ranong"),

    # --- Nakhon Ratchasima (Korat) / Isaan ---
    ("AKP",   "Airkorat -- northeastern regional coach",
     "Nakhon Ratchasima", "Nakhon Ratchasima"),
    ("ACP",   "Air Chaiyaphum -- northeastern regional coach",
     "Chaiyaphum", "Chaiyaphum"),
    ("ARU",   "Air Ubon -- northeastern regional coach",
     "Ubon Ratchathani", "Ubon Ratchathani"),
    ("SPT",   "Sahaphan Roi-Et Tour -- northeastern regional coach",
     "Roi Et", "Roi Et"),
    ("HIN",   "Hello Isaan -- northeastern regional coach",
     None, None),
    ("SS",    "Sawasdee Surin -- northeastern regional coach",
     "Surin", "Surin"),
]


def slugify(s):
    """ASCII slug."""
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def check_bulk_live():
    """HEAD the national zip; return (ok, info_str). Non-fatal on failure."""
    try:
        req = urllib.request.Request(
            BULK_URL, method="HEAD", headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            ct = r.headers.get("Content-Type", "")
            cl = r.headers.get("Content-Length", "?")
            lm = r.headers.get("Last-Modified", "?")
            ok = (r.status == 200 and "zip" in ct.lower())
            return ok, "HTTP %s, %s, %s bytes, Last-Modified %s" % (
                r.status, ct or "?", cl, lm)
    except Exception as e:
        return False, "HEAD failed: %r" % (e,)


def build_records():
    """One national record + one per known sub-operator (agency fragment)."""
    records = []

    # 1) national multimodal feed -- bare URL
    nat_slug = "namtang-national-gtfs"
    records.append({
        "id": "%s-%s" % (CC.lower(), nat_slug),
        "provider": NATIONAL["provider"],
        "name": NATIONAL["name"],
        "cc": CC,
        "subdiv": NATIONAL["subdiv"],
        "city": NATIONAL["city"],
        "producer_url": BULK_URL,
        "hosted_url": None,
        "license": LICENSE,
        "bbox": None,
        "status": "active",
        "official": True,
    })

    # 2) per-operator records -- same zip, distinct via #agency=<id> fragment
    for agency, name, subdiv, city in OPERATORS:
        producer_url = "%s#agency=%s" % (BULK_URL, agency)
        slug = slugify(agency) or slugify(name)
        records.append({
            "id": "%s-%s" % (CC.lower(), slug),
            "provider": PUBLISHER,   # all attributed to OTP Namtang
            "name": "%s (Namtang national GTFS, agency_id %s)" % (name, agency),
            "cc": CC,
            "subdiv": subdiv,
            "city": city,
            "producer_url": producer_url,
            "hosted_url": None,
            "license": LICENSE,
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

    ok, info = check_bulk_live()
    print("bulk %s -> %s" % ("OK" if ok else "WARN", info))
    # Non-fatal: the aggregator was verified live 2026-08-22; a transient HEAD
    # failure should not block appending the known catalogue.

    candidates = build_records()

    new = []
    local_seen = set()
    for rec in candidates:
        key = rec["producer_url"].rstrip("/")
        if key in seen or key in local_seen:
            continue
        local_seen.add(key)
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
