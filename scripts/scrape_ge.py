#!/usr/bin/env python3
"""
Scraper: Georgia (GE) — Transitous (public-transport/transitous) national manifest.

Provenance notes (verified 2026-08-22):
  * Georgia is NOT an EU member, so there is NO legally-mandated National Access
    Point and no official government open-transit portal.
  * Tbilisi Transport Company (ttc.com.ge) publishes NO GTFS export — it only
    exposes a private REST/real-time API (transit.ttc.com.ge), which 403s to
    anonymous clients.
  * The de-facto national machine-readable access point is the Transitous
    project's per-country manifest feeds/ge.json. It self-hosts cleaned/fixed
    GTFS at jbb.ghsq.de/gtfs/ (ge-*.gtfs.zip) and re-serves processed feeds at
    api.transitous.org/gtfs/. Feeds were freshly rebuilt (last-modified
    2026-08-21/22), i.e. actively maintained.
  * Mobility Database has little/no GE coverage; Transitland only has US-state-
    of-Georgia feeds (name collision) — neither is used here.

This scraper fetches the JSON manifest, iterates the top-level "sources" array,
and emits one catalog record per STATIC GTFS source (spec != "gtfs-rt"). As of
2026-08 that yields:
  1. Georgian Railway (ge-georgian-railway.gtfs.zip, ODbL-1.0) — nationwide rail
  2. Tbilisi Transport Company (ge-tbilisi.gtfs.zip) — metro/bus/minibus/ropeway

stdlib only (json, urllib, os, re). Appends to data/feeds_full.json, dedup by
producer_url (rstrip('/')). Prints '+N new GE feeds'.
"""

import json
import os
import re
import urllib.request
import urllib.error

SRC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "feeds_full.json",
)

CC = "GE"
TIMEOUT = 30

MANIFEST_URL = (
    "https://raw.githubusercontent.com/public-transport/transitous/main/"
    "feeds/ge.json"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "*/*",
}

# Per-source human enrichment (provider name, display title, subdiv, city).
# Keyed by the manifest source "name". Sources not listed here still get a
# sane auto-generated record from their slug — nothing is dropped.
ENRICH = {
    "georgian-railway": {
        "provider": "Georgian Railway (Sakartvelos Rkinigza) - intercity rail",
        "name": (
            "Georgian Railway GTFS (nationwide intercity rail incl. "
            "Tbilisi-Batumi, Tbilisi-Kutaisi/Zugdidi) - Transitous"
        ),
        "subdiv": None,
        "city": None,
    },
    "tbilisi-transport-company": {
        "provider": (
            "Tbilisi Transport Company (TTC) - metro, city bus, minibus, ropeway"
        ),
        "name": (
            "Tbilisi (TTC) GTFS (metro + city bus + minibus + ropeways) - "
            "Transitous cleaned feed"
        ),
        "subdiv": "Tbilisi",
        "city": "Tbilisi",
    },
}


def slugify(s):
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def load_existing():
    try:
        with open(SRC, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except (FileNotFoundError, ValueError):
        pass
    return []


def http_get_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception:
        return None


def url_ok(url):
    """Verify the GTFS URL resolves (200) and looks like a zip / binary."""
    # Try HEAD first; fall back to a ranged GET (some hosts reject HEAD).
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(url, headers=dict(HEADERS), method=method)
        if method == "GET":
            req.add_header("Range", "bytes=0-0")
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                if r.status not in (200, 206):
                    continue
                ct = (r.headers.get("Content-Type") or "").lower()
                if ("zip" in ct or "octet-stream" in ct or "binary" in ct
                        or ct == ""):
                    return True
                # Some hosts mislabel; a .gtfs.zip URL is trustworthy enough.
                return url.lower().endswith(".zip")
        except urllib.error.HTTPError as e:
            if e.code in (403, 405, 501) and method == "HEAD":
                continue  # host dislikes HEAD; try GET
            return False
        except Exception:
            continue
    # Last resort: don't drop a known .zip feed on a flaky probe.
    return url.lower().endswith(".zip")


def extract_license(src):
    """Manifest license is nested: {"license": {"spdx-identifier": "ODbL-1.0"}}."""
    lic = src.get("license")
    if isinstance(lic, dict):
        return lic.get("spdx-identifier") or lic.get("url") or None
    if isinstance(lic, str) and lic.strip():
        return lic.strip()
    return None


def make_record(rec_id, provider, name, subdiv, city, producer_url, license_):
    return {
        "id": rec_id,
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


def build_candidates(manifest):
    """One record per static GTFS source (spec != 'gtfs-rt') in the manifest."""
    out = []
    sources = manifest.get("sources") if isinstance(manifest, dict) else None
    if not isinstance(sources, list):
        return out
    for src in sources:
        if not isinstance(src, dict):
            continue
        # Skip realtime feeds — we only catalog static GTFS.
        if (src.get("spec") or "").lower() == "gtfs-rt":
            continue
        url = src.get("url")
        if not isinstance(url, str) or not url.startswith("http"):
            continue
        name = src.get("name") or ""
        slug = slugify(name) or slugify(url.rsplit("/", 1)[-1])
        enr = ENRICH.get(name, {})
        provider = enr.get("provider") or (name.replace("-", " ").title()
                                           if name else "Unknown operator")
        title = enr.get("name") or (
            (provider + " GTFS - Transitous").strip()
        )
        out.append(
            make_record(
                CC.lower() + "-" + slug,
                provider,
                title,
                enr.get("subdiv"),
                enr.get("city"),
                url,
                extract_license(src),
            )
        )
    return out


def main():
    existing = load_existing()
    seen = {
        r.get("producer_url", "").rstrip("/")
        for r in existing
        if isinstance(r, dict)
    }

    manifest = http_get_json(MANIFEST_URL)
    if not manifest:
        print("+0 new {cc} feeds".format(cc=CC))
        return

    candidates = build_candidates(manifest)

    added = 0
    for rec in candidates:
        url = rec.get("producer_url") or ""
        key = url.rstrip("/")
        if not key or key in seen:
            continue
        if not url_ok(url):
            continue
        existing.append(rec)
        seen.add(key)
        added += 1

    with open(SRC, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    print("+{n} new {cc} feeds".format(n=added, cc=CC))


if __name__ == "__main__":
    main()
