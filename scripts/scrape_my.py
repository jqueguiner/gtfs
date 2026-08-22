#!/usr/bin/env python3
"""
Malaysia (MY) GTFS feed scraper.

Source
------
data.gov.my — Malaysia's Official Open API, GTFS Static service
(https://developer.data.gov.my/realtime-api/gtfs-static).

A single authoritative national REST host, api.data.gov.my, serves official
GTFS Static ZIPs for ALL Malaysian operators via a documented, fixed URL
scheme. There is NO queryable JSON feed-index — the agency/category list *is*
the documentation — so this scraper iterates a hardcoded endpoint list against
the base host and validates each one at run time.

Endpoint families (verified 2026-08-22):
  1. ktmb                      -> /gtfs-static/ktmb            (national rail)
  2. prasarana?category=<cat>  -> /gtfs-static/prasarana?category=<cat>
       cat in {rapid-rail-kl, rapid-bus-kl, rapid-bus-penang,
               rapid-bus-kuantan, rapid-bus-mrtfeeder}
  3. mybas-<city>              -> /gtfs-static/mybas-<city>    (BAS.MY stage bus)
       city in {kangar, alor-setar, kota-bharu, kuala-terengganu, ipoh,
                seremban-a, seremban-b, melaka, johor, kuching}
       (Seremban has TWO operators: query both -a and -b.)

Each endpoint 301-redirects to a trailing-slash URL then returns HTTP 200 with
Content-Type binary/octet-stream (or application/zip); the response bytes ARE
the GTFS .zip directly (no wrapper JSON). urllib follows the 301 automatically.
No API key required.

Robustness: each endpoint is fetched with a timeout, and only accepted if it
returns HTTP 200 whose body begins with the ZIP local-file-header magic (PK\\x03
\\x04). Failures (e.g. rapid-bus-kuantan currently 404s with a JSON error body)
are logged and skipped, so newly-added agencies are picked up automatically and
not-yet-live ones do no harm. Dedup is by producer_url (rstrip('/')).

Each record appended to data/feeds_full.json has EXACTLY these keys:
  id, provider, name, cc, subdiv, city, producer_url, hosted_url,
  license, bbox, status, official
Stdlib only (json, urllib.request, os, re).
"""

import json
import os
import re
import urllib.request

try:
    import fcntl  # POSIX; used to serialize concurrent scraper writes.
except ImportError:  # pragma: no cover - non-POSIX fallback
    fcntl = None

CC = "MY"
UA = "Mozilla/5.0 (compatible; gtfs-catalog/1.0; +https://github.com/jqueguiner/gtfs)"
TIMEOUT = 90
# data.gov.my publishes under the Malaysia Government open-data terms (CC-BY 4.0).
LICENSE = "CC-BY-4.0"

BASE = "https://api.data.gov.my/gtfs-static"

SRC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "feeds_full.json",
)

# Endpoint catalog. Each entry:
#   (url, provider, name, subdiv, city)
# The url is the documented clean form; api.data.gov.my 301-redirects it to the
# trailing-slash canonical URL, which urllib follows transparently.
ENDPOINTS = [
    # --- KTMB: national rail (Komuter / ETS / intercity) ---
    (
        BASE + "/ktmb",
        "KTMB (Keretapi Tanah Melayu Berhad)",
        "KTMB — KTM Komuter / ETS / intercity rail (national, GTFS Static)",
        None, "Kuala Lumpur",
    ),
    # --- Prasarana: Klang Valley rail + Rapid Bus network ---
    (
        BASE + "/prasarana?category=rapid-rail-kl",
        "Prasarana Malaysia Berhad — Rapid Rail",
        "Prasarana Rapid Rail KL — LRT Kelana Jaya / LRT Ampang & Sri Petaling "
        "/ KL Monorail / MRT Kajang / MRT Putrajaya (GTFS Static)",
        "Selangor", "Kuala Lumpur",
    ),
    (
        BASE + "/prasarana?category=rapid-bus-kl",
        "Prasarana Malaysia Berhad — Rapid Bus",
        "Prasarana Rapid Bus KL — RapidKL stage buses (GTFS Static)",
        "Selangor", "Kuala Lumpur",
    ),
    (
        BASE + "/prasarana?category=rapid-bus-mrtfeeder",
        "Prasarana Malaysia Berhad — Rapid Bus",
        "Prasarana Rapid Bus — MRT Feeder buses (GTFS Static)",
        "Selangor", "Kuala Lumpur",
    ),
    (
        BASE + "/prasarana?category=rapid-bus-penang",
        "Prasarana Malaysia Berhad — Rapid Bus",
        "Prasarana Rapid Bus Penang — Rapid Penang stage buses (GTFS Static)",
        "Penang", "George Town",
    ),
    (
        BASE + "/prasarana?category=rapid-bus-kuantan",
        "Prasarana Malaysia Berhad — Rapid Bus",
        "Prasarana Rapid Bus Kuantan (GTFS Static)",
        "Pahang", "Kuantan",
    ),
    # --- BAS.MY (myBAS): federally-funded stage bus, per city ---
    (
        BASE + "/mybas-kangar",
        "BAS.MY (myBAS)",
        "BAS.MY (myBAS) Kangar — stage bus (GTFS Static)",
        "Perlis", "Kangar",
    ),
    (
        BASE + "/mybas-alor-setar",
        "BAS.MY (myBAS)",
        "BAS.MY (myBAS) Alor Setar — stage bus (GTFS Static)",
        "Kedah", "Alor Setar",
    ),
    (
        BASE + "/mybas-kota-bharu",
        "BAS.MY (myBAS)",
        "BAS.MY (myBAS) Kota Bharu — stage bus (GTFS Static)",
        "Kelantan", "Kota Bharu",
    ),
    (
        BASE + "/mybas-kuala-terengganu",
        "BAS.MY (myBAS)",
        "BAS.MY (myBAS) Kuala Terengganu — stage bus (GTFS Static)",
        "Terengganu", "Kuala Terengganu",
    ),
    (
        BASE + "/mybas-ipoh",
        "BAS.MY (myBAS)",
        "BAS.MY (myBAS) Ipoh — stage bus (GTFS Static)",
        "Perak", "Ipoh",
    ),
    (
        BASE + "/mybas-seremban-a",
        "BAS.MY (myBAS)",
        "BAS.MY (myBAS) Seremban (operator A) — stage bus (GTFS Static)",
        "Negeri Sembilan", "Seremban",
    ),
    (
        BASE + "/mybas-seremban-b",
        "BAS.MY (myBAS)",
        "BAS.MY (myBAS) Seremban (operator B) — stage bus (GTFS Static)",
        "Negeri Sembilan", "Seremban",
    ),
    (
        BASE + "/mybas-melaka",
        "BAS.MY (myBAS)",
        "BAS.MY (myBAS) Melaka — stage bus (GTFS Static)",
        "Melaka", "Melaka",
    ),
    (
        BASE + "/mybas-johor",
        "BAS.MY (myBAS)",
        "BAS.MY (myBAS) Johor Bahru — stage bus (GTFS Static)",
        "Johor", "Johor Bahru",
    ),
    (
        BASE + "/mybas-kuching",
        "BAS.MY (myBAS)",
        "BAS.MY (myBAS) Kuching — stage bus (GTFS Static)",
        "Sarawak", "Kuching",
    ),
]


def slugify(s):
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "feed"


def endpoint_slug(url):
    """Stable slug from the endpoint path/query (e.g. prasarana-rapid-bus-kl)."""
    m = re.sub(r"^https?://[^/]+/gtfs-static/", "", url)
    m = m.replace("?category=", "-").replace("category=", "")
    return slugify(m)


def is_live_zip(url):
    """GET the endpoint (following redirects) and confirm HTTP 200 + ZIP magic.

    Returns True only if the body starts with the ZIP local-file-header magic
    'PK\\x03\\x04'. Any network/HTTP error or non-zip body -> False.
    """
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            if getattr(r, "status", 200) != 200:
                return False
            head = r.read(4)
            return head[:4] == b"PK\x03\x04"
    except Exception as e:
        print("  skip %s (%s)" % (url, e))
        return False


def scrape():
    for url, provider, name, subdiv, city in ENDPOINTS:
        if not is_live_zip(url):
            continue
        yield {
            "id": "%s-%s" % (CC.lower(), endpoint_slug(url)),
            "provider": provider,
            "name": name,
            "cc": CC,
            "subdiv": subdiv,
            "city": city,
            "producer_url": url,
            "hosted_url": None,
            "license": LICENSE,
            "bbox": None,
            "status": "active",
            "official": True,
        }


def _load(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, ValueError):
        return []


def commit(candidates):
    """Merge `candidates` into the catalog under an exclusive lock.

    The catalog is written by many country scrapers in parallel; a naive
    read-modify-write races and silently drops records (last writer wins). We
    therefore hold an exclusive fcntl lock across the ENTIRE read -> dedup ->
    write cycle and re-read the file *inside* the lock so we merge against the
    freshest on-disk state. The write itself goes to a temp file + os.replace
    for atomicity (no partial/corrupt catalog for concurrent readers).
    """
    os.makedirs(os.path.dirname(SRC), exist_ok=True)
    lock_path = SRC + ".lock"
    lf = open(lock_path, "w")
    try:
        if fcntl is not None:
            fcntl.flock(lf.fileno(), fcntl.LOCK_EX)

        existing = _load(SRC)
        have = set()
        for rec in existing:
            pu = (rec.get("producer_url") or "").rstrip("/")
            if pu:
                have.add(pu)

        added = []
        seen_new = set()
        for rec in candidates:
            pu = (rec.get("producer_url") or "").rstrip("/")
            if not pu or pu in have or pu in seen_new:
                continue
            seen_new.add(pu)
            added.append(rec)

        if added:
            existing.extend(added)
            tmp = SRC + ".tmp.%d" % os.getpid()
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(existing, fh, ensure_ascii=False, indent=2)
            os.replace(tmp, SRC)
        return added
    finally:
        if fcntl is not None:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
        lf.close()


def main():
    # Do all network I/O BEFORE taking the lock, to keep the lock-hold short.
    candidates = list(scrape())
    added = commit(candidates)
    print("+%d new %s feeds" % (len(added), CC))


if __name__ == "__main__":
    main()
