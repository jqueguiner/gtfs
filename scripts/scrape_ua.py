#!/usr/bin/env python3
"""
Scraper: Ukraine (UA) — data.gov.ua National Open Data Portal (CKAN) + EasyWay pattern.

Ukraine is NOT an EU member and has NO EU-style single-file National Access Point
(no NeTEx, no MobilityData bulk index). The real machine-readable access point is
the national open-data portal data.gov.ua, a standard CKAN instance whose Action
API enumerates every dataset carrying the GTFS / vehicle_position tag:

  GET https://data.gov.ua/api/3/action/package_search?q=GTFS&rows=100
      -> {"success": true, "result": {"count": N, "results": [ <package>, ... ]}}

Each <package> has:
  - "title" / "name"                     (dataset title + slug)
  - "license_id" / "license_title"       (mostly cc-by)
  - "organization": {"title": ...}       (the publishing city council / operator)
  - "resources": [ {"url","name","format","description"}, ... ]

EasyWay (eway.in.ua) is the de-facto national transit-data operator for ~73 UA
cities, and track.ua-gis.com / city.dozor.tech host the EasyWay GTFS static+RT
for cities that opened their data — but EasyWay exposes NO open bulk listing API,
so feeds only surface per city through data.gov.ua. Real-time vehicle positions
are suppressed in many cities for wartime security reasons.

Discovery strategy (all network I/O first, commit under lock last):

  1. CKAN q=GTFS and q=vehicle_position (union, dedup by package id). For each
     resource, classify:
       - STATIC  : format in {ZIP, GTFS} and url ends .zip, OR name/description
                   mentions "gtfs static" / "gtfsstatic", OR a known static
                   endpoint (…/static.zip, export-gtfs-static).
       - RT       : url ends .proto, OR name/format mentions vehicle_position /
                    realtime / tripupdates, OR a known RT endpoint.
     We aggressively EXCLUDE non-transit noise the vehicle_position query pulls in
     (freight-vehicle registries "vehicles.zip", ArcGIS f=… query URLs, xlsx/csv
     stop-lists, opendata.gov.ua route spreadsheets).

  2. Probe the EasyWay host patterns for a curated city-slug list to catch feeds
     that are live but whose data.gov.ua resource URL is indirect:
       http://track.ua-gis.com/gtfs/{slug}/static.zip   (Lviv, Uzhhorod, …)
       https://city.dozor.tech/{slug}/gtfs/static.zip    (Rivne, Ivano-Frankivsk, …)
     Only HTTP-200 hits are emitted.

  3. Always emit the documented official Kyivpastrans GTFS-static endpoint
     (http://193.23.225.211:8002/export-gtfs-static). It requires an HTTP POST
     (GET/HEAD -> 405/422) so it can't be HEAD-probed; it is a known-good
     published endpoint, so we include it unconditionally.

Each record is one operator feed. producer_url is the DIRECT GTFS zip / RT / POST
endpoint. Dedup is by producer_url.rstrip('/') against the existing catalog.

VERIFIED live 2026-08-22:
  Lviv static.zip HTTP200 3.7MB; Uzhhorod static.zip HTTP200 451KB;
  Rivne / Ivano-Frankivsk dozor.tech static.zip HTTP200; Chornomorsk zip HTTP200;
  Kyiv export-gtfs-static POST endpoint (422 to GET, expected); Sumy / Lviv /
  Dnipro / Chervonohrad RT feeds enumerated from CKAN.

The catalog is written by many country scrapers in parallel; a naive
read-modify-write races and drops records. We do all network I/O first, then
commit under an exclusive fcntl lock (SRC + ".lock") with an in-lock re-read and
a per-pid temp file + os.replace for atomicity — matching the repo pattern.

stdlib only (json, urllib, os, re). Appends to data/feeds_full.json (a JSON
array), dedup by producer_url (rstrip('/')). Prints '+N new UA feeds'.
"""

import json
import os
import re
import urllib.request
import urllib.error

try:
    import fcntl  # POSIX; serialize concurrent scraper writes.
except ImportError:
    fcntl = None

SRC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "feeds_full.json",
)

CC = "UA"
TIMEOUT = 45
UA_HDR = "Mozilla/5.0 (compatible; gtfs-catalog-scraper/1.0)"
HEADERS = {"User-Agent": UA_HDR, "Accept": "*/*"}

CKAN_QUERIES = [
    "https://data.gov.ua/api/3/action/package_search?q=GTFS&rows=100",
    "https://data.gov.ua/api/3/action/package_search?q=vehicle_position&rows=100",
]

# EasyWay host patterns to probe per known city slug. Only HTTP-200 hits emitted.
TRACK_TPL = "http://track.ua-gis.com/gtfs/{slug}/static.zip"
DOZOR_TPL = "https://city.dozor.tech/{slug}/gtfs/static.zip"

# slug -> (city display name, subdiv/oblast). Broad list; 404s are skipped.
CITY_SLUGS = {
    "lviv": ("Lviv", "Lviv Oblast"),
    "uzhhorod": ("Uzhhorod", "Zakarpattia Oblast"),
    "rivne": ("Rivne", "Rivne Oblast"),
    "iv-frankivsk": ("Ivano-Frankivsk", "Ivano-Frankivsk Oblast"),
    "ivano-frankivsk": ("Ivano-Frankivsk", "Ivano-Frankivsk Oblast"),
    "ternopil": ("Ternopil", "Ternopil Oblast"),
    "lutsk": ("Lutsk", "Volyn Oblast"),
    "khmelnytskyi": ("Khmelnytskyi", "Khmelnytskyi Oblast"),
    "zhytomyr": ("Zhytomyr", "Zhytomyr Oblast"),
    "cherkasy": ("Cherkasy", "Cherkasy Oblast"),
    "chernihiv": ("Chernihiv", "Chernihiv Oblast"),
    "chernivtsi": ("Chernivtsi", "Chernivtsi Oblast"),
    "poltava": ("Poltava", "Poltava Oblast"),
    "vinnytsia": ("Vinnytsia", "Vinnytsia Oblast"),
    "kropyvnytskyi": ("Kropyvnytskyi", "Kirovohrad Oblast"),
    "mykolaiv": ("Mykolaiv", "Mykolaiv Oblast"),
    "sumy": ("Sumy", "Sumy Oblast"),
    "zaporizhia": ("Zaporizhzhia", "Zaporizhzhia Oblast"),
    "chervonohrad": ("Chervonohrad", "Lviv Oblast"),
}

# Documented official Kyivpastrans static endpoint (POST-only, always emit).
KYIV_STATIC = {
    "url": "http://193.23.225.211:8002/export-gtfs-static",
    "provider": "Kyivpastrans (Kyivpastrans АСДУ)",
    "name": "Kyiv public transport — GTFS static (Kyivpastrans)",
    "city": "Kyiv",
    "subdiv": "Kyiv",
    "license": "CC-BY-4.0",
}

# Non-transit noise the vehicle_position query pulls in — exclude by url substring.
URL_BLOCK = (
    "arcgis", "gisserver", "mapserver", "/query?", "f=geojson", "f=pjson",
    "opendata.gov.ua",  # freight / route spreadsheets, not GTFS
    "vehicles.zip", "vehicles-",  # Ukrtransbezpeka freight-vehicle registry
    ".xlsx", ".csv", ".geojson", "devices.json",
    "/routes", "eway.in.ua",  # human-facing route map pages
)

CITY_HINTS = [
    ("lviv", "Lviv", "Lviv Oblast"),
    ("uzhhorod", "Uzhhorod", "Zakarpattia Oblast"),
    ("rivne", "Rivne", "Rivne Oblast"),
    ("frankivsk", "Ivano-Frankivsk", "Ivano-Frankivsk Oblast"),
    ("frankivs", "Ivano-Frankivsk", "Ivano-Frankivsk Oblast"),
    ("sumy", "Sumy", "Sumy Oblast"),
    ("chornomorsk", "Chornomorsk", "Odesa Oblast"),
    ("dnipro", "Dnipro", "Dnipropetrovsk Oblast"),
    ("chervonograd", "Chervonohrad", "Lviv Oblast"),
    ("chervonohrad", "Chervonohrad", "Lviv Oblast"),
    ("kyiv", "Kyiv", "Kyiv"),
    ("kiev", "Kyiv", "Kyiv"),
    # Kyivpastrans АСДУ servers are on these fixed IPs (data.gov.ua Kyiv datasets).
    ("193.23.225.211", "Kyiv", "Kyiv"),
    ("193.23.225.214", "Kyiv", "Kyiv"),
    ("46.4.68.233", "Dnipro", "Dnipropetrovsk Oblast"),
]

SPDX = {
    "cc-by": "CC-BY-4.0",
    "cc-by-4.0": "CC-BY-4.0",
    "cc-zero": "CC0-1.0",
    "cc0": "CC0-1.0",
    "other-open": None,
    "": None,
    None: None,
}


def load_existing():
    if not os.path.exists(SRC):
        return []
    try:
        with open(SRC, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (ValueError, OSError):
        return []


def slugify(s):
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "feed"


def fetch_json(url):
    req = urllib.request.Request(url, headers={**HEADERS, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def head_ok(url):
    """True if a GET returns HTTP 200 (used to probe EasyWay static.zip patterns)."""
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status == 200
    except urllib.error.HTTPError:
        return False
    except Exception:
        return False


def classify(res):
    """Return 'static', 'rt' or None for a CKAN resource dict."""
    url = (res.get("url") or "").strip()
    if not url:
        return None
    low = url.lower()
    for bad in URL_BLOCK:
        if bad in low:
            return None
    name = (res.get("name") or "").lower()
    fmt = (res.get("format") or "").strip().lower()
    desc = (res.get("description") or "").lower()
    blob = " ".join((name, fmt, desc))

    # RT: protobuf / vehicle_position / realtime endpoints.
    if low.endswith(".proto") or "/vehicle_position" in low or "/api/realtime" in low:
        return "rt"
    if any(k in blob for k in ("vehicle_position", "vehicleposition", "realtime",
                               "real-time", "tripupdate", "gtfs-rt", "gtfs realtime")):
        # but a "GTFS static" resource may also mention realtime in the dataset
        # title; only treat as RT if it's clearly not a zip payload.
        if not low.endswith(".zip"):
            return "rt"

    # STATIC: zip payloads or known static endpoints.
    if low.endswith("static.zip") or "export-gtfs-static" in low:
        return "static"
    if low.endswith(".zip") and (fmt in ("zip", "gtfs") or "gtfs" in blob):
        return "static"
    if ("gtfs static" in blob or "gtfsstatic" in blob) and low.startswith("http"):
        return "static"
    return None


def guess_city(*texts):
    hay = " ".join(t or "" for t in texts).lower()
    for key, city, sub in CITY_HINTS:
        if key in hay:
            return city, sub
    return None, None


def main():
    existing = load_existing()
    seen = set()
    for r in existing:
        pu = r.get("producer_url")
        if pu:
            seen.add(pu.rstrip("/"))

    new_records = []
    used_ids = set(r.get("id") for r in existing if r.get("id"))

    def unique_id(base):
        base = "{}-{}".format(CC.lower(), slugify(base))
        cand, n = base, 2
        while cand in used_ids:
            cand = "{}-{}".format(base, n)
            n += 1
        used_ids.add(cand)
        return cand

    def add(*, producer_url, provider, name, city, subdiv, license, id_hint):
        if not producer_url:
            return
        key = producer_url.rstrip("/")
        if key in seen:
            return
        seen.add(key)
        new_records.append({
            "id": unique_id(id_hint),
            "provider": provider,
            "name": name,
            "cc": CC,
            "subdiv": subdiv,
            "city": city,
            "producer_url": producer_url,
            "hosted_url": None,
            "license": license,
            "bbox": None,
            "status": "active",
            "official": True,
        })

    # ---- (1) CKAN discovery (union of the two queries, dedup by package id) ----
    packages = {}
    for qurl in CKAN_QUERIES:
        try:
            d = fetch_json(qurl)
        except Exception:
            continue
        if not d.get("success"):
            continue
        for p in (d.get("result", {}) or {}).get("results", []) or []:
            pid = p.get("id") or p.get("name")
            if pid and pid not in packages:
                packages[pid] = p

    for p in packages.values():
        org = (p.get("organization") or {}).get("title") or "Ukraine open transit"
        title = p.get("title") or p.get("name") or "GTFS"
        lic = SPDX.get((p.get("license_id") or "").lower(), None)
        for res in p.get("resources", []) or []:
            kind = classify(res)
            if not kind:
                continue
            url = res.get("url").strip()
            city, subdiv = guess_city(res.get("name"), res.get("description"),
                                      title, url)
            if kind == "rt":
                fname = "{} — GTFS-RT ({})".format(
                    city or "Ukraine", res.get("name") or "vehicle positions")
                add(producer_url=url, provider=org, name=fname, city=city,
                    subdiv=subdiv, license=lic,
                    id_hint="{}-rt-{}".format(city or org, res.get("name") or "vp"))
            else:  # static
                fname = "{} — GTFS static".format(city or title[:60])
                add(producer_url=url, provider=org, name=fname, city=city,
                    subdiv=subdiv, license=lic,
                    id_hint="{}-gtfs-static".format(city or slugify(title)[:40]))

    # ---- (2) Kyivpastrans official POST-only static endpoint (always emit) ----
    add(producer_url=KYIV_STATIC["url"], provider=KYIV_STATIC["provider"],
        name=KYIV_STATIC["name"], city=KYIV_STATIC["city"],
        subdiv=KYIV_STATIC["subdiv"], license=KYIV_STATIC["license"],
        id_hint="kyiv-gtfs-static")

    # ---- (3) Probe EasyWay host patterns per city slug (only HTTP 200) ----
    probed = set()
    for slug, (city, subdiv) in CITY_SLUGS.items():
        for tpl in (TRACK_TPL, DOZOR_TPL):
            url = tpl.format(slug=slug)
            key = url.rstrip("/")
            if key in seen or key in probed:
                continue
            probed.add(key)
            if not head_ok(url):
                continue
            add(producer_url=url,
                provider="{} via EasyWay".format(city),
                name="{} — GTFS static (EasyWay)".format(city),
                city=city, subdiv=subdiv, license="CC-BY-4.0",
                id_hint="{}-easyway-static".format(slug))

    # ---- Commit under exclusive lock (re-read inside lock; atomic replace) ----
    lock_path = SRC + ".lock"
    lock_f = None
    if fcntl is not None:
        try:
            lock_f = open(lock_path, "w")
            fcntl.flock(lock_f, fcntl.LOCK_EX)
        except OSError:
            lock_f = None

    try:
        current = load_existing()
        cur_seen = set()
        for r in current:
            pu = r.get("producer_url")
            if pu:
                cur_seen.add(pu.rstrip("/"))
        cur_ids = set(r.get("id") for r in current if r.get("id"))

        added = 0
        for rec in new_records:
            key = rec["producer_url"].rstrip("/")
            if key in cur_seen:
                continue
            # ensure id uniqueness against the freshly re-read catalog
            if rec["id"] in cur_ids:
                base, n = rec["id"], 2
                while rec["id"] in cur_ids:
                    rec["id"] = "{}-{}".format(base, n)
                    n += 1
            cur_ids.add(rec["id"])
            cur_seen.add(key)
            current.append(rec)
            added += 1

        tmp = "{}.tmp.{}".format(SRC, os.getpid())
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(current, f, ensure_ascii=False, indent=2)
        os.replace(tmp, SRC)
    finally:
        if lock_f is not None:
            try:
                fcntl.flock(lock_f, fcntl.LOCK_UN)
                lock_f.close()
            except OSError:
                pass

    print("+{} new {} feeds".format(added, CC))


if __name__ == "__main__":
    main()