#!/usr/bin/env python3
"""Scraper for Turkey (TR) open-transit GTFS feeds.

Turkey is a non-EU country with NO EU-style mandated National Access Point.
TRota (the national MaaS platform) exposes no open feed repository. De-facto
programmatic access is via the CKAN Action APIs of the two richest municipal
open-data portals:

  (1) IZMIR — https://acikveri.bizizmir.com/api/3/action/package_search?q=gtfs
      A single dataset 'toplu-ulasim-gtfs-verileri' whose resources[] are 5
      direct per-operator GTFS zips (eshot/izban/izmirmetro/tramizmir/izdeniz).
      We take every resource with format=='ZIP' and read its 'url' field.

  (2) ISTANBUL — https://data.ibb.gov.tr/api/3/action/package_search?q=gtfs
      Two datasets:
        - iett-gtfs-verisi (id 8540e256-6df5-4719-85bc-e64e91508ede): the full
          22MB GTFS bundle is the resource whose download filename is
          'stop_times.zip' (format ZIP). Its sibling CSV resources are the
          unpacked GTFS files and are NOT emitted (not a feed zip).
        - public-transport-gtfs-data (id 121a9892-...): multi-operator GTFS as
          individual CSV resources only (no bundle zip). Marked "will not be
          updated". No zip resource is present, so it is skipped with a WARN
          (schema requires a direct GTFS zip in producer_url).

  (3) B40 CITIES mirror (optional dedup) —
      https://opendata.b40cities.org/api/3/action/package_search?q=gtfs
      CKAN mirror; only orgs 'istanbul' & 'izmir' are TR-relevant (rest are
      Balkan cities). The host serves an incomplete TLS chain, so we fetch it
      with an unverified SSL context. Any TR-org ZIP/GTFS resource url found is
      added; dedup by producer_url removes overlaps with (1)/(2). Failures are
      non-fatal and skipped.

  (4) KOCAELI — fixed static GTFS zip (Mobility Database mdb-1122). Included
      unconditionally; it is TR-geo-gated (returns 000 from non-TR hosts) but is
      a stable, known-good producer URL.

Only records with a real, resolvable direct GTFS zip URL are appended. Dedup is
by producer_url (rstrip('/')). stdlib only (json, urllib.request, os, re, ssl).
Appends to data/feeds_full.json. Prints '+N new TR feeds'.

Ankara/EGO, Bursa, Konya, Gaziantep, Antalya, Adana have no scrapable open
GTFS today and are intentionally not emitted.
"""
import json
import os
import re
import ssl
import urllib.request
import urllib.error

CC = "TR"
UA = "Mozilla/5.0 (compatible; gtfs-catalog-scraper/1.0)"
TIMEOUT = 45

SRC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "feeds_full.json",
)

IZMIR_API = "https://acikveri.bizizmir.com/api/3/action/package_search?q=gtfs&rows=50"
ISTANBUL_API = "https://data.ibb.gov.tr/api/3/action/package_search?q=gtfs&rows=50"
B40_API = "https://opendata.b40cities.org/api/3/action/package_search?q=gtfs&rows=100"

IETT_PKG_ID = "8540e256-6df5-4719-85bc-e64e91508ede"

# TLS-tolerant context (some TR hosts / the B40 mirror serve incomplete chains).
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

# Per-operator metadata for the Izmir single dataset, keyed by download host.
# Lets us assign a clean provider/city instead of the Turkish resource name.
IZMIR_OPERATORS = {
    "eshot.gov.tr": {"provider": "ESHOT", "note": "buses"},
    "izban.com.tr": {"provider": "IZBAN", "note": "commuter rail"},
    "izmirmetro.com.tr": {"provider": "Izmir Metro", "note": "metro"},
    "tramizmir.com": {"provider": "Tram Izmir", "note": "tram"},
    "izdeniz.com.tr": {"provider": "Izdeniz", "note": "ferries"},
}

# Fixed feeds not exposed via a scrapable CKAN API (static/geo-gated).
FIXED_FEEDS = [
    {
        "slug": "kocaeli",
        "provider": "Kocaeli Buyuksehir Belediyesi",
        "name": "Kocaeli GTFS — bus/tram/BRT (mdb-1122)",
        "subdiv": "Kocaeli",
        "city": "Kocaeli",
        "producer_url": "http://kocaeli.bel.tr/webfiles/userfiles/files/"
        "birimler/bilgi-islem-dairesi-baskanligi/kocaeli-gtfs.zip",
        "license": None,
    },
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


def fetch_json(url):
    """GET a CKAN Action API url and return parsed JSON, or None on failure."""
    headers = {"User-Agent": UA, "Accept": "application/json"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=_SSL_CTX) as resp:
            body = resp.read()
        data = json.loads(body.decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        print("WARN: {} -> HTTP {} (skip)".format(url, e.code))
        return None
    except Exception as e:
        print("WARN: {} -> {} (skip)".format(url, e))
        return None
    if not isinstance(data, dict) or not data.get("success"):
        print("WARN: {} -> non-success CKAN payload (skip)".format(url))
        return None
    return data


def ckan_packages(data):
    """Return result.results[] as a list (robust to shape)."""
    if not data:
        return []
    result = data.get("result") or {}
    results = result.get("results")
    return results if isinstance(results, list) else []


def is_gtfs_zip_resource(res):
    """True if a CKAN resource is a GTFS zip bundle (by format or url suffix)."""
    fmt = (res.get("format") or "").strip().lower()
    url = (res.get("url") or "").strip()
    if not url:
        return False
    if fmt == "zip":
        return True
    if url.lower().endswith(".zip"):
        return True
    return False


def rec(slug, provider, name, subdiv, city, producer_url, license_=None):
    return {
        "id": "{}-{}".format(CC.lower(), slug),
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


def collect_izmir():
    """Izmir CKAN: one dataset, 5 direct operator GTFS zips (format==ZIP)."""
    records = []
    data = fetch_json(IZMIR_API)
    if data is None:
        return records
    pkgs = ckan_packages(data)
    for pkg in pkgs:
        for res in pkg.get("resources") or []:
            if not is_gtfs_zip_resource(res):
                continue
            url = res["url"].strip()
            host = re.sub(r"^www\.", "", (re.sub(r"^https?://", "", url).split("/")[0]))
            meta = IZMIR_OPERATORS.get(host)
            if meta:
                provider = meta["provider"]
                note = meta["note"]
                slug = "izmir-" + slugify(provider)
                name = "{} GTFS ({}) — Izmir, via acikveri.bizizmir.com".format(
                    provider, note
                )
            else:
                # Unknown operator: derive from host, still emit it.
                base = host.split(".")[0] or "operator"
                provider = base
                slug = "izmir-" + slugify(base)
                name = "{} GTFS — Izmir, via acikveri.bizizmir.com".format(provider)
            records.append(
                rec(
                    slug=slug,
                    provider=provider,
                    name=name,
                    subdiv="Izmir",
                    city="Izmir",
                    producer_url=url,
                    license_=pkg.get("license_title") or pkg.get("license_id"),
                )
            )
    if not records:
        print("WARN: Izmir CKAN returned no ZIP resources")
    return records


def collect_istanbul():
    """Istanbul CKAN: IETT full-bundle zip + any other ZIP resources."""
    records = []
    data = fetch_json(ISTANBUL_API)
    if data is None:
        return records
    pkgs = ckan_packages(data)
    for pkg in pkgs:
        pkg_id = pkg.get("id") or ""
        pkg_title = pkg.get("name") or pkg.get("title") or ""
        lic = pkg.get("license_title") or pkg.get("license_id")
        zip_res = [r for r in (pkg.get("resources") or []) if is_gtfs_zip_resource(r)]
        if not zip_res:
            # e.g. public-transport-gtfs-data: CSV-only, no bundle zip -> skip.
            print(
                "WARN: Istanbul pkg '{}' has no ZIP bundle (CSV-only), skipping".format(
                    pkg_title or pkg_id
                )
            )
            continue
        for res in zip_res:
            url = res["url"].strip()
            if pkg_id == IETT_PKG_ID or "iett" in pkg_title.lower():
                provider = "IETT (Istanbul Electricity Tramway & Tunnel)"
                name = "IETT GTFS — Istanbul buses/metrobus/tram (full bundle)"
                slug = "istanbul-iett"
            else:
                provider = "IBB ({})".format(pkg_title or "Istanbul public transport")
                name = "Istanbul GTFS — {} (via data.ibb.gov.tr)".format(
                    pkg_title or "public transport"
                )
                slug = "istanbul-" + slugify(pkg_title or pkg_id[:8])
            records.append(
                rec(
                    slug=slug,
                    provider=provider,
                    name=name,
                    subdiv="Istanbul",
                    city="Istanbul",
                    producer_url=url,
                    license_=lic,
                )
            )
    if not records:
        print("WARN: Istanbul CKAN returned no ZIP resources")
    return records


def collect_b40():
    """B40 Cities mirror: only TR orgs (istanbul/izmir). Optional; dedup handles
    overlap with the primary portals. Failures are non-fatal."""
    records = []
    data = fetch_json(B40_API)
    if data is None:
        return records
    tr_orgs = {"istanbul", "izmir"}
    for pkg in ckan_packages(data):
        org = pkg.get("organization") or {}
        org_name = (org.get("name") or "").lower()
        org_title = org.get("title") or org.get("name") or ""
        if org_name not in tr_orgs:
            continue
        city = "Istanbul" if org_name == "istanbul" else "Izmir"
        lic = pkg.get("license_title") or pkg.get("license_id")
        for res in pkg.get("resources") or []:
            if not is_gtfs_zip_resource(res):
                continue
            url = res["url"].strip()
            rname = (res.get("name") or org_title or "gtfs").strip()
            records.append(
                rec(
                    slug="b40-" + slugify(org_name + "-" + rname)[:40],
                    provider="{} (B40 mirror)".format(org_title or org_name),
                    name="{} GTFS ({}) — via opendata.b40cities.org".format(
                        org_title or org_name, city
                    ),
                    subdiv=city,
                    city=city,
                    producer_url=url,
                    license_=lic,
                )
            )
    return records


def main():
    existing = load_existing()
    seen = set()
    for r in existing:
        pu = r.get("producer_url")
        if pu:
            seen.add(pu.rstrip("/"))

    candidates = []
    candidates.extend(collect_izmir())
    candidates.extend(collect_istanbul())
    candidates.extend(collect_b40())
    for d in FIXED_FEEDS:
        candidates.append(
            rec(
                slug=d["slug"],
                provider=d["provider"],
                name=d["name"],
                subdiv=d["subdiv"],
                city=d["city"],
                producer_url=d["producer_url"],
                license_=d["license"],
            )
        )

    added = 0
    for r in candidates:
        pu = r.get("producer_url")
        if not pu:
            continue
        key = pu.rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        existing.append(r)
        added += 1

    os.makedirs(os.path.dirname(SRC), exist_ok=True)
    with open(SRC, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    print("+{} new {} feeds".format(added, CC))


if __name__ == "__main__":
    main()
