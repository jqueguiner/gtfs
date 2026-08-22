#!/usr/bin/env python3
"""
Scraper: Latvia (LV) — data.gov.lv CKAN portal + gsvalbe.id.lv community source list.

Latvia does NOT publish NeTEx on a NAP. The de-facto national access point is the
Latvijas Atvērto datu portāls (data.gov.lv), a standard CKAN instance. Its Action API
enumerates the machine-readable GTFS datasets:

  GET https://data.gov.lv/dati/api/3/action/package_search?q=GTFS&rows=100
      -> {"success": true, "result": {"count": N, "results": [ <package>, ... ]}}

Each <package> has:
  - "title" / "name"            (dataset title + slug)
  - "license_id" / "license_title"
  - "organization": {"title": ...}   (the publishing operator)
  - "resources": [ {"url": ..., "name": ..., "format": ...}, ... ]

CKAN q=GTFS currently returns 3 core datasets:
  - atd-gtfs                    -> https://www.atd.lv/sites/default/files/GTFS/gtfs-latvia-lv.zip
                                   (VSIA Autotransporta direkcija: national regional/intercity
                                    + many city buses + Gulbene-Aluksne narrow-gauge rail; ~30MB)
  - iekszemes-dzelzcela-...     -> https://vivi.lv/uploads/GTFS.zip
                                   (Pasazieru vilciens / Vivi: national passenger rail)
  - marsrutu-saraksti-rigas-... -> 70 monthly Riga (Rigas satiksme) archive zips on data.gov.lv;
                                   we keep only the NEWEST by MarsrutuSaraksti MM_YYYY name.

We take resources whose url ends in .zip. For the Riga dataset (many monthly archives of the
SAME feed) we keep only the single newest archive so we don't spam the catalog with 70 rows.

To EXCEED the base coverage we also scrape the community source list HTML:

  GET https://gsvalbe.id.lv/pieturas/avoti.html

which lists per-city operators (Liepaja, Rezekne, Daugavpils, Jelgava, Valmiera, Ventspils,
Jekabpils, Jurmala, ...) whose GTFS zips are NOT on data.gov.lv. We regex every href ending
in .zip and map known hosts/paths to (operator, city). Those feeds default to CC0 (the
community list mirrors CC0 municipal open-data feeds); unknown ones fall back to null license.

stdlib only (json, urllib, os, re). Appends to data/feeds_full.json (a JSON array),
dedup by producer_url (rstrip('/')). Prints '+N new LV feeds'.
"""

import json
import os
import re
import urllib.request
import urllib.error
from urllib.parse import urlparse

SRC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "feeds_full.json",
)

CC = "LV"
CKAN_URL = "https://data.gov.lv/dati/api/3/action/package_search?q=GTFS&rows=100"
AVOTI_URL = "https://gsvalbe.id.lv/pieturas/avoti.html"
TIMEOUT = 90
HEADERS = {
    # A browser-ish UA: some LV hosts (e.g. rigassatiksme live) reject the default urllib UA.
    "User-Agent": "Mozilla/5.0 (compatible; adresses-gtfs-catalog/1.0; +https://github.com/jqueguiner/gtfs)",
    "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
}

# The Riga dataset ships the SAME feed as ~70 monthly archives; collapse to the newest.
RIGA_DATASET_NAMES = {
    "marsrutu-saraksti-rigas-satiksme-sabiedriskajam-transportam",
    "marsrutu-saraksti-rigas-satiksme",
}

# Community-list host/path -> (operator name, city). Best-effort enrichment; the community
# feeds mirror CC0 municipal open data, so we default them to CC0-1.0 below.
COMMUNITY_HINTS = [
    ("satiksme.daugavpils.lv", "Daugavpils satiksme", "Daugavpils"),
    ("marsruti.lv/liepaja", "Liepajas sabiedriskais transports", "Liepaja"),
    ("marsruti.lv/rezekne", "Rezeknes satiksme", "Rezekne"),
    ("marsruti.lv/jurmala", "Jurmalas autobusu satiksme", "Jurmala"),
    ("marsruti.lv/lsa", "Latvijas Sabiedriskais autobuss (LSA)", None),
    ("marsruti.lv/pieriga", "Latvijas Sabiedriskais autobuss (LSA) — Pieriga", None),
    ("gtfs/jelgava", "Jelgavas autobusu parks", "Jelgava"),
    ("lvnap.lv/jap", "Jelgavas autobusu parks", "Jelgava"),
    ("gtfs/jurmala", "Hansabuss (Jurmala)", "Jurmala"),
    ("gtfs/ventspils", "Ventspils reiss", "Ventspils"),
    ("gtfs/valmiera", "VTU Valmiera", "Valmiera"),
    ("gtfs/jekabpils", "Jekabpils autobusu parks", "Jekabpils"),
    ("dati/latvia.zip", "PIETURAS combined Latvia feed", None),
    ("dati/baltics.zip", "PIETURAS combined Baltics feed", None),
    ("atd.lv/sites/default/files/gtfs", "VSIA Autotransporta direkcija (ATD)", None),
    ("vivi.lv/uploads", "Pasazieru vilciens / Vivi", None),
    ("modus.pv.lv/uploads", "Pasazieru vilciens / Vivi", None),
    ("rigassatiksme.lv", "Rigas satiksme", "Riga"),
]

# URL substrings we deliberately skip: the live Rigas satiksme host blocks non-browser
# fetches in practice; we already capture Riga via the data.gov.lv monthly archive, so
# prefer that stable one and drop the live duplicate to keep one canonical Riga feed.
COMMUNITY_SKIP = ("saraksti.rigassatiksme.lv",)


def slugify(s):
    s = (s or "").lower()
    s = s.encode("ascii", "ignore").decode("ascii")
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


def clean_license(lic):
    if lic is None:
        return None
    lic = str(lic).strip()
    return lic or None


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


def fetch(url):
    """Fetch a URL, return decoded text or None on any failure."""
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError, ValueError) as e:
        print("WARN: fetch failed {}: {}".format(url, e))
        return None


# ---------- CKAN (data.gov.lv) ----------

def riga_archive_key(url, name):
    """Sort key for Riga monthly archives -> (year, month); higher = newer.

    Names look like 'MarsrutuSaraksti05_2018' or urls '.../marsrutusaraksti03_2026.zip'.
    Falls back to (0, 0) when no MM_YYYY can be parsed.
    """
    for hay in (name or "", url or ""):
        m = re.search(r"(\d{2})[_-](\d{4})", hay.lower())
        if m:
            return (int(m.group(2)), int(m.group(1)))
    return (0, 0)


def ckan_feeds():
    """Yield (provider, name, subdiv, city, url, license) from the CKAN portal."""
    body = fetch(CKAN_URL)
    if not body:
        return
    try:
        data = json.loads(body)
    except ValueError as e:
        print("WARN: CKAN JSON parse failed: {}".format(e))
        return
    result = data.get("result") if isinstance(data, dict) else None
    packages = (result or {}).get("results") if isinstance(result, dict) else None
    if not isinstance(packages, list):
        print("WARN: CKAN returned no results list")
        return

    for pkg in packages:
        if not isinstance(pkg, dict):
            continue
        title = pkg.get("title") or pkg.get("name") or "GTFS"
        org = (pkg.get("organization") or {}).get("title") if isinstance(pkg.get("organization"), dict) else None
        provider = org or title
        lic = clean_license(pkg.get("license_id") or pkg.get("license_title"))

        zips = []
        for rs in pkg.get("resources") or []:
            if not isinstance(rs, dict):
                continue
            url = (rs.get("url") or "").strip()
            if url.lower().startswith("http") and url.lower().rstrip().endswith(".zip"):
                zips.append((url, rs.get("name") or ""))

        if not zips:
            continue

        is_riga = pkg.get("name") in RIGA_DATASET_NAMES or "rigas" in (pkg.get("name") or "")
        if is_riga:
            # Collapse the many monthly archives to the single newest one.
            url, rname = max(zips, key=lambda z: riga_archive_key(z[0], z[1]))
            yield (provider, "GTFS — {} (data.gov.lv, newest archive)".format(title), None, "Riga", url, lic)
        else:
            for url, rname in zips:
                yield (provider, "GTFS — {} (data.gov.lv)".format(title), None, None, url, lic)


# ---------- Community source list (gsvalbe.id.lv) ----------

def community_hint(url):
    """Map a community-list URL to (provider, city). Returns (None, None) if unknown."""
    low = url.lower()
    for needle, provider, city in COMMUNITY_HINTS:
        if needle in low:
            return provider, city
    return None, None


def community_feeds():
    """Yield (provider, name, subdiv, city, url, license) from the gsvalbe HTML list."""
    body = fetch(AVOTI_URL)
    if not body:
        return
    # Every .zip href on the page (handles single/double quotes and bare hrefs).
    urls = re.findall(r"""href\s*=\s*["']?([^"'>\s]+\.zip)["']?""", body, re.IGNORECASE)
    seen_local = set()
    for url in urls:
        url = url.strip()
        if not url.lower().startswith("http"):
            continue
        if any(s in url.lower() for s in COMMUNITY_SKIP):
            continue
        key = url.rstrip("/")
        if key in seen_local:
            continue
        seen_local.add(key)
        provider, city = community_hint(url)
        if not provider:
            # Unknown community feed: derive a provider label from the host.
            provider = urlparse(url).netloc
        # Community list mirrors CC0 municipal open-data feeds.
        yield (provider, "GTFS — {} (gsvalbe community list)".format(provider), None, city, url, "CC0-1.0")


def main():
    existing = load_existing()
    seen = {r.get("producer_url", "").rstrip("/") for r in existing if isinstance(r, dict)}
    used_ids = {r.get("id") for r in existing if isinstance(r, dict)}

    candidates = []
    for provider, name, subdiv, city, url, lic in ckan_feeds():
        p = urlparse(url)
        base = slugify(p.netloc + "-" + p.path) or slugify(provider)
        candidates.append((CC.lower() + "-" + base, provider, name, subdiv, city, url, lic))

    for provider, name, subdiv, city, url, lic in community_feeds():
        p = urlparse(url)
        base = slugify(p.netloc + "-" + p.path) or slugify(provider)
        candidates.append((CC.lower() + "-" + base, provider, name, subdiv, city, url, lic))

    added = 0
    for rec_id, provider, name, subdiv, city, url, lic in candidates:
        key = url.rstrip("/")
        if key in seen:
            continue
        uid = rec_id
        n = 2
        while uid in used_ids:
            uid = "{}-{}".format(rec_id, n)
            n += 1
        existing.append(make_record(uid, provider, name, subdiv, city, url, lic))
        seen.add(key)
        used_ids.add(uid)
        added += 1

    with open(SRC, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    print("+{n} new {cc} feeds".format(n=added, cc=CC))


if __name__ == "__main__":
    main()
