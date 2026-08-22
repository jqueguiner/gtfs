#!/usr/bin/env python3
"""
Scraper: South Korea (KR) — TAGO National Public Transportation Information
Center (국가대중교통정보센터, MOLIT/KOTSA) via the data.go.kr Public Data Portal,
plus the confirmed real nationwide/regional GTFS feeds that actually exist as
downloadable files.

Reality of KR open transit (why this scraper is shaped the way it is)
--------------------------------------------------------------------
South Korea has NO EU-style legally-mandated NAP exposing a single bulk GTFS
download. The de-facto national aggregator is TAGO (run by MOLIT + the Korea
Transportation Safety Authority, KOTSA), published as ~13 REST datasets on
data.go.kr under provider id 1613000 (base host apis.data.go.kr/1613000/...).
Those datasets are JSON/XML, **NOT GTFS** — there is no field that returns a
ready GTFS zip. A genuine nationwide GTFS static exists only via KTDB
(ktdb.go.kr) through a manual Information-Disclosure data request (no direct
URL); a community mirror of that dataset is published on Hugging Face.

Verified endpoint shapes (probed live)
--------------------------------------
  * TAGO city-code list (JSON):
      GET https://apis.data.go.kr/1613000/BusRouteInfoInqireService/
          getCtyCodeList?serviceKey=KEY&_type=json&numOfRows=1000
    success -> response.body.items.item[] = [{"citycode":25, "cityname":"대전"}...]
    error   -> {"OpenAPI_ServiceResponse":{"cmmMsgHeader":{"errMsg":...}}}
    (with no/invalid key: returnReasonCode 30 SERVICE_KEY_IS_NOT_REGISTERED)
  * KTDB nationwide GTFS community mirror (HEAD verified: 302 -> 200,
    content-type application/zip, content-length ~470 MB):
      https://huggingface.co/datasets/Digital-Twin-Urban-Mobility/
      GTFS-Korea/resolve/main/GTFS_Korea.zip

Strategy
--------
1. CORE feeds: always append the confirmed real, directly-downloadable KR GTFS
   feed(s) — the KTDB nationwide GTFS (HF mirror). These have a resolvable
   producer_url (a real GTFS .zip), which is what the catalog wants.
2. TAGO enumeration (needs a free serviceKey; register on data.go.kr, dev quota
   10,000 calls/day): if a key is present in env (TAGO_SERVICE_KEY /
   DATA_GO_KR_KEY / SERVICE_KEY), call getCtyCodeList and synthesize ONE feed
   record per TAGO city, whose producer_url is the stable, per-city TAGO
   BusRouteInfoInqireService query (the source you must ETL to GTFS). This
   covers every city TAGO exposes in a single pass (Busan, Daegu, Daejeon,
   Gwangju, Ulsan, and all provincial cities — but NOT Seoul/Gyeonggi/Incheon,
   which run their own APIs outside TAGO). Without a key the scraper still
   succeeds, appending just the CORE feed(s).

stdlib only (json, urllib, os, re). Appends to data/feeds_full.json, dedup by
producer_url (rstrip('/')). Prints '+N new KR feeds'.
"""

import json
import os
import re
import urllib.parse
import urllib.request
import urllib.error

SRC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "feeds_full.json",
)

CC = "KR"
TIMEOUT = 30
HEADERS = {"User-Agent": "adresses-gtfs-catalog/1.0 (+https://gladia.io)"}

# ---------------------------------------------------------------------------
# TAGO REST (data.go.kr provider 1613000)
# ---------------------------------------------------------------------------
TAGO_BASE = "https://apis.data.go.kr/1613000"
TAGO_CTY_LIST = (
    TAGO_BASE + "/BusRouteInfoInqireService/getCtyCodeList"
)
# The per-city route-list operation is the canonical source you ETL into GTFS.
TAGO_ROUTE_LIST = (
    TAGO_BASE + "/BusRouteInfoInqireService/getRouteNoList"
)


def _service_key():
    for env in ("TAGO_SERVICE_KEY", "DATA_GO_KR_KEY", "SERVICE_KEY", "DATA_GO_KR_SERVICE_KEY"):
        v = os.environ.get(env)
        if v:
            return v.strip()
    return None


# ---------------------------------------------------------------------------
# CORE: confirmed real, directly downloadable KR GTFS feeds
# ---------------------------------------------------------------------------
CORE = [
    {
        "slug": "ktdb-nationwide-gtfs",
        "provider": "KTDB — Korea Transport DataBase (MOLIT), community mirror",
        "name": (
            "GTFS Korea — nationwide static (city/village bus, urban rail, "
            "intercity/express bus, conventional+high-speed rail, airport "
            "limousine, coastal shipping, domestic air)"
        ),
        "subdiv": None,
        "city": None,
        # HEAD verified: 302 -> 200, content-type application/zip, ~470 MB.
        "url": (
            "https://huggingface.co/datasets/Digital-Twin-Urban-Mobility/"
            "GTFS-Korea/resolve/main/GTFS_Korea.zip"
        ),
        # HF dataset carries no explicit license tag; KTDB pilot data.
        "license": None,
    },
]


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
    s = (s or "").strip().lower()
    # transliterate-free: keep ascii alnum, collapse the rest to hyphens.
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s


def make_record(rid, provider, name, subdiv, city, producer_url, license_):
    return {
        "id": rid,
        "provider": provider,
        "name": name,
        "cc": CC,
        "subdiv": subdiv,
        "city": city,
        "producer_url": producer_url,
        "hosted_url": None,
        "license": license_,
        "bbox": None,
        "status": "active",
        "official": True,
    }


def http_get_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        raw = resp.read().decode("utf-8", "replace")
    return json.loads(raw)


def fetch_tago_cities(key):
    """Return list of {'citycode':str,'cityname':str} from TAGO, or []."""
    params = urllib.parse.urlencode(
        {"serviceKey": key, "_type": "json", "numOfRows": "1000", "pageNo": "1"},
        safe="%",  # serviceKey may already be URL-encoded; don't double-encode.
    )
    url = TAGO_CTY_LIST + "?" + params
    try:
        data = http_get_json(url)
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, OSError):
        return []

    # Error envelope -> no cities.
    if isinstance(data, dict) and "OpenAPI_ServiceResponse" in data:
        hdr = (
            data["OpenAPI_ServiceResponse"].get("cmmMsgHeader", {})
            if isinstance(data["OpenAPI_ServiceResponse"], dict)
            else {}
        )
        msg = hdr.get("errMsg") or hdr.get("returnAuthMsg") or "unknown error"
        print("  ! TAGO getCtyCodeList error: {0}".format(msg))
        return []

    try:
        body = data["response"]["body"]
        header = data["response"].get("header", {})
        # result code guard
        rc = header.get("resultCode")
        if rc not in (None, "00", "0", 0):
            print("  ! TAGO resultCode {0}: {1}".format(rc, header.get("resultMsg")))
            return []
        items = body["items"]["item"]
    except (KeyError, TypeError):
        return []

    if isinstance(items, dict):  # single item -> wrap
        items = [items]
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        code = it.get("citycode")
        name = it.get("cityname")
        if code is None or not name:
            continue
        out.append({"citycode": str(code).strip(), "cityname": str(name).strip()})
    return out


# TAGO does NOT cover these metros with its own bus APIs (they run separate
# systems); if they ever appear in the city list we skip synthesizing a TAGO
# feed for them to avoid a misleading source.
_NON_TAGO_METRO_CODES = set()  # citycodes are numeric; none known-excluded by code


def build_tago_records(cities):
    out = []
    for c in cities:
        code = c["citycode"]
        name = c["cityname"]
        if code in _NON_TAGO_METRO_CODES:
            continue
        # Stable per-city producer URL = the route-list query you ETL to GTFS.
        # Uses a placeholder {serviceKey} so the URL is deterministic and
        # dedup-stable across runs regardless of which key produced it.
        producer_url = (
            TAGO_ROUTE_LIST
            + "?serviceKey={serviceKey}&_type=json&cityCode="
            + urllib.parse.quote(code)
        )
        city_ascii = slugify(name) or ("city-" + code)
        rid = "{cc}-tago-{code}-{slug}".format(
            cc=CC.lower(), code=code, slug=city_ascii
        )
        provider = "TAGO — National Public Transportation Information Center (MOLIT/KOTSA)"
        feed_name = (
            "TAGO bus routes/stops — {name} (cityCode {code}) "
            "[REST JSON, ETL to GTFS]".format(name=name, code=code)
        )
        out.append(
            make_record(
                rid,
                provider,
                feed_name,
                None,     # subdiv unknown from city list
                name,     # city name (native)
                producer_url,
                # data.go.kr default terms; not a fixed SPDX id.
                None,
            )
        )
    return out


def main():
    existing = load_existing()
    seen = {
        r.get("producer_url", "").rstrip("/")
        for r in existing
        if isinstance(r, dict) and r.get("producer_url")
    }

    candidates = []

    # 1) CORE real downloadable feed(s).
    for c in CORE:
        candidates.append(
            make_record(
                CC.lower() + "-" + c["slug"],
                c["provider"],
                c["name"],
                c["subdiv"],
                c["city"],
                c["url"],
                c["license"],
            )
        )

    # 2) TAGO per-city enumeration (needs a free serviceKey).
    key = _service_key()
    if key:
        cities = fetch_tago_cities(key)
        print("  TAGO cities enumerated: {0}".format(len(cities)))
        candidates.extend(build_tago_records(cities))
    else:
        print(
            "  (no serviceKey in env [TAGO_SERVICE_KEY/DATA_GO_KR_KEY/SERVICE_KEY]; "
            "skipping TAGO per-city enumeration — appending CORE feed(s) only. "
            "Register a free key on data.go.kr to enumerate all TAGO cities.)"
        )

    added = 0
    for rec in candidates:
        key_ = rec["producer_url"].rstrip("/")
        if not key_ or key_ in seen:
            continue
        existing.append(rec)
        seen.add(key_)
        added += 1

    with open(SRC, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    print("+{n} new {cc} feeds".format(n=added, cc=CC))


if __name__ == "__main__":
    main()
