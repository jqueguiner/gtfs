#!/usr/bin/env python3
"""Scraper for Taiwan (TW) open-transit GTFS feeds.

Source: TDX — Transport Data eXchange
        Ministry of Transportation and Communications (MOTC)
        https://tdx.transportdata.tw/  (successor to PTX, sunset 2022-12-01)

TDX is Taiwan's official national open-transit access point. Its GTFS Service
(Beta) exposes nationwide static GTFS covering High Speed Rail (THSR), Taiwan
Railway (TRA), intercity + city buses, MRT/metro, light rail, ferries and
gondola, plus GTFS-Realtime. There is ONE nationwide bulk GTFS zip covering all
operators/modes, and per-rail-operator zips.

Endpoints (from the V3 OpenAPI, id 7eeb6468-9935-4f12-be82-b2224bda3879):
    Download_03001  GET /api/gtfs/V3/Map/GTFS/Static
                    -> nationwide GTFS zip (ALL operators, all modes)
    Download_03002  GET /api/gtfs/V3/Map/GTFS/Static/Rail/{OperatorCode}
                    -> per-rail-operator GTFS zip
                    OperatorCode in the enum below (12 rail operators).

AUTH: every endpoint requires OIDC client-credentials auth. To actually pull the
zip bytes you POST client_id + client_secret to the TDX Keycloak token endpoint,
read access_token, then GET the resource with 'authorization: Bearer <token>'.
Set TDX_CLIENT_ID / TDX_CLIENT_SECRET in the environment to enable live
verification (HEAD/GET) of each feed; without them the scraper still records the
canonical direct producer_url for every feed the API exposes (auth is a fetch-
time concern, the URLs are stable and enumerated by the OpenAPI spec).

stdlib only (json, urllib, os, re). Appends records to data/feeds_full.json.
"""
import json
import os
import re
import urllib.request
import urllib.parse
import urllib.error

CC = "TW"
BASE = "https://tdx.transportdata.tw"
TOKEN_URL = BASE + "/auth/realms/TDXConnect/protocol/openid-connect/token"
NATIONAL_URL = BASE + "/api/gtfs/V3/Map/GTFS/Static"
RAIL_URL_TMPL = BASE + "/api/gtfs/V3/Map/GTFS/Static/Rail/{code}"
LICENSE = "Open Government Data License, version 1.0 (Taiwan)"
UA = "gtfs-catalog-scraper/1.0"
TIMEOUT = 60

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'feeds_full.json')

# Per-rail-operator codes enumerated by the TDX V3 OpenAPI (Download_03002).
# code -> (English provider name, region/subdiv, primary city, feed title tag)
RAIL_OPERATORS = [
    ("TRA",    "Taiwan Railways Administration (TRA)",        None,                   None,           "Taiwan Railway"),
    ("THSR",   "Taiwan High Speed Rail Corporation (THSR)",   None,                   None,           "High Speed Rail"),
    ("TRTC",   "Taipei Rapid Transit Corporation (TRTC)",     "Taipei",               "Taipei",       "Taipei Metro / MRT"),
    ("KRTC",   "Kaohsiung Rapid Transit Corporation (KRTC)",  "Kaohsiung",            "Kaohsiung",    "Kaohsiung Metro / MRT"),
    ("TYMC",   "Taoyuan Metro Corporation (TYMC)",            "Taoyuan",              "Taoyuan",      "Taoyuan Metro (incl. Airport MRT)"),
    ("KLRT",   "Kaohsiung Rapid Transit Corp. — Light Rail",  "Kaohsiung",            "Kaohsiung",    "Kaohsiung Light Rail"),
    ("NTDLRT", "New Taipei Metro — Danhai LRT",               "New Taipei",           "New Taipei",   "Danhai (Tamsui) Light Rail"),
    ("TMRT",   "Taichung Rapid Transit Corporation (TMRT)",   "Taichung",             "Taichung",     "Taichung MRT"),
    ("NTMC",   "New Taipei Metro Corporation (NTMC)",         "New Taipei",           "New Taipei",   "New Taipei Metro"),
    ("TRTCMG", "Taipei Rapid Transit — Maokong Gondola",      "Taipei",               "Taipei",       "Maokong Gondola"),
    ("NTALRT", "New Taipei Metro — Ankeng LRT",               "New Taipei",           "New Taipei",   "Ankeng Light Rail"),
    ("AFR",    "Alishan Forest Railway (AFR)",                "Chiayi",               "Chiayi",       "Alishan Forest Railway"),
]


def slugify(s):
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def load_existing():
    if not os.path.exists(SRC):
        return []
    try:
        with open(SRC, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (ValueError, OSError):
        return []


def get_token():
    """OIDC client-credentials -> access_token, or None if creds absent/failed."""
    cid = os.environ.get("TDX_CLIENT_ID")
    secret = os.environ.get("TDX_CLIENT_SECRET")
    if not cid or not secret:
        return None
    body = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": cid,
        "client_secret": secret,
    }).encode("ascii")
    req = urllib.request.Request(
        TOKEN_URL,
        data=body,
        headers={
            "content-type": "application/x-www-form-urlencoded",
            "User-Agent": UA,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
        return data.get("access_token")
    except Exception as e:
        print("WARN: TDX token request failed: {}".format(e))
        return None


def verify(url, token):
    """Best-effort liveness check of a feed URL. Returns True if it looks live.

    Only run when we hold a token; a 200 (zip bytes) confirms the feed. Any
    network/HTTP failure returns False but never aborts the scrape.
    """
    if not token:
        return None  # unknown / not checked
    req = urllib.request.Request(
        url,
        headers={"authorization": "Bearer " + token, "User-Agent": UA},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            # Read a small chunk to confirm a body without pulling the whole zip.
            resp.read(64)
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as e:
        print("WARN: verify {} -> HTTP {}".format(url, e.code))
        return False
    except Exception as e:
        print("WARN: verify {} -> {}".format(url, e))
        return False


def build_records():
    records = []

    # 1) Nationwide bulk feed (all operators / all modes) — Download_03001.
    records.append({
        "id": "{}-tdx-national-gtfs".format(CC.lower()),
        "provider": "TDX — Transport Data eXchange (MOTC)",
        "name": "TDX national GTFS (all operators: bus + rail + LRT + ferry, nationwide)",
        "cc": CC,
        "subdiv": None,
        "city": None,
        "producer_url": NATIONAL_URL,
        "hosted_url": None,
        "license": LICENSE,
        "bbox": None,
        "status": "active",
        "official": True,
    })

    # 2) Per-rail-operator feeds — Download_03002.
    for code, provider, subdiv, city, tag in RAIL_OPERATORS:
        url = RAIL_URL_TMPL.format(code=code)
        records.append({
            "id": "{}-tdx-rail-{}".format(CC.lower(), slugify(code)),
            "provider": provider,
            "name": "TDX GTFS — {} ({})".format(tag, code),
            "cc": CC,
            "subdiv": subdiv,
            "city": city,
            "producer_url": url,
            "hosted_url": None,
            "license": LICENSE,
            "bbox": None,
            "status": "active",
            "official": True,
        })

    return records


def main():
    existing = load_existing()
    seen = set()
    for r in existing:
        pu = r.get("producer_url")
        if pu:
            seen.add(pu.rstrip("/"))

    token = get_token()  # optional; enables live verification only
    if token:
        print("INFO: TDX token acquired; verifying feed liveness.")
    else:
        print("INFO: no TDX creds (TDX_CLIENT_ID/TDX_CLIENT_SECRET); "
              "recording enumerated feeds without live verification.")

    candidates = build_records()

    added = 0
    for rec in candidates:
        key = rec["producer_url"].rstrip("/")
        if key in seen:
            continue
        # If we have a token, drop feeds that verify as dead; otherwise keep all.
        if token is not None:
            ok = verify(rec["producer_url"], token)
            if ok is False:
                continue
        seen.add(key)
        existing.append(rec)
        added += 1

    os.makedirs(os.path.dirname(SRC), exist_ok=True)
    with open(SRC, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    print("+{} new {} feeds".format(added, CC))


if __name__ == "__main__":
    main()