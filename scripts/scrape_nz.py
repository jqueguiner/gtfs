#!/usr/bin/env python3
"""
Scraper: New Zealand (NZ) — no mandated national GTFS access point.

NZ has NO single legally-mandated GTFS aggregator and no national bulk GTFS zip.
Each regional council / PTA publishes its own producer GTFS zip (Auckland Transport,
Metlink/GW, Waikato BUSIT, BOP Baybus, Horizons, Otago ORC, Metro Christchurch, etc.).
The Waka Kotahi NZTA open-data ArcGIS Hub covers roads/traffic/crash data, NOT PT
schedules, so it is useless for GTFS.

The only key-free, programmatic enumeration of NZ producer feeds is the
Transitland Atlas (github.com/transitland/transitland-atlas), whose DMFR files are
named per producer domain (e.g. at.govt.nz.dmfr.json, metlink.org.nz.dmfr.json).
Each DMFR file has a `feeds` array; a GTFS static feed has spec="gtfs" and
`urls.static_current` (the direct producer zip). Operator names live in the feed's
`operators[].name`, and the licence in `license.spdx_identifier`.

The Transitland REST API (api.transit.land/.../feeds?adm0_iso=NZ) and the Mobility
Database both require an API key / bearer token, so we do NOT use them. Instead we
read the Atlas DMFR JSON directly from the jsdelivr CDN (no key, no auth). If the
network / CDN is unavailable we fall back to a verified hardcoded list so the run
still populates the catalog.

Tier 1: fetch the known NZ-domain DMFR files, parse each gtfs feed's static_current.
Tier 2 (fallback / union): a verified hardcoded list of NZ producer feeds.

We keep only feeds published under an NZ producer domain (*.nz) — Transitland reuses
some vendor DMFRs (e.g. connexionz.net) that also carry US/CA operators, which we
must not attribute to NZ.

stdlib only (json, os, re, urllib). Appends to data/feeds_full.json (a JSON array),
dedup by producer_url (rstrip('/')). Prints '+N new NZ feeds'.
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

CC = "NZ"
TIMEOUT = 30
HEADERS = {
    "User-Agent": "adresses-gtfs-catalog/1.0 (+https://github.com/jqueguiner/gtfs)",
    "Accept": "application/json, */*",
}

# Transitland Atlas DMFR files that carry NZ producer feeds. Named by producer domain.
# Read key-free from the jsdelivr CDN mirror of the github repo.
ATLAS_BASE = "https://cdn.jsdelivr.net/gh/transitland/transitland-atlas@master/feeds/"
NZ_DMFR_FILES = [
    "at.govt.nz",          # Auckland Transport (AT Metro): bus/rail/ferry — largest NZ feed
    "metlink.org.nz",      # Metlink (Greater Wellington RC): bus/rail/cable car/ferry
    "baybus.co.nz",        # Bayhopper/Baybus (Bay of Plenty RC): Tauranga/Rotorua/Whakatane
    "busit.co.nz",         # BUSIT (Waikato Regional Council): Hamilton
    "horizons.govt.nz",    # Connect / Horizons RC (Manawatu-Whanganui): Palmerston North
    "orc.govt.nz",         # Otago Regional Council: Dunedin + Queenstown (Bee Card)
    "metroinfo.co.nz",     # Metro Christchurch (Environment Canterbury) + Metro Timaru
]

# Region / city hints keyed by producer domain, so records carry subdiv + city.
DOMAIN_HINTS = {
    "at.govt.nz":       ("Auckland", "Auckland"),
    "metlink.org.nz":   ("Wellington", "Wellington"),
    "baybus.co.nz":     ("Bay of Plenty", "Tauranga"),
    "busit.co.nz":      ("Waikato", "Hamilton"),
    "horizons.govt.nz": ("Manawatu-Whanganui", "Palmerston North"),
    "orc.govt.nz":      ("Otago", "Dunedin"),
    "metroinfo.co.nz":  ("Canterbury", "Christchurch"),
}

# Tier-2 verified fallback (union with tier-1). Producer zips resolved from the Atlas
# DMFR on 2026-08-22; Auckland+Metlink+BUSIT+Otago verified live 200/206.
# Fields: (slug, provider, name, subdiv, city, producer_url, license)
FALLBACK = [
    ("auckland-transport",
     "Auckland Transport (AT Metro)",
     "Auckland Transport GTFS (bus, rail, ferry)",
     "Auckland", "Auckland",
     "https://gtfs.at.govt.nz/gtfs.zip", "CC-BY-4.0"),
    ("metlink-wellington",
     "Metlink (Greater Wellington Regional Council)",
     "Metlink GTFS (bus, rail, cable car, ferry)",
     "Wellington", "Wellington",
     "https://static.opendata.metlink.org.nz/v1/gtfs/full.zip", "CC-BY-4.0"),
    ("baybus-bay-of-plenty",
     "Bayhopper / Baybus (Bay of Plenty Regional Council)",
     "Baybus / Bayhopper GTFS (Tauranga, Rotorua, Whakatane, rural BOP)",
     "Bay of Plenty", "Tauranga",
     "https://faqs.baybus.co.nz/hc/en-nz/article_attachments/9375750637839", "CC-BY-4.0"),
    ("busit-waikato",
     "BUSIT (Waikato Regional Council)",
     "BUSIT GTFS (Hamilton, Waikato)",
     "Waikato", "Hamilton",
     "https://wrcscheduledata.blob.core.windows.net/wrcgtfs/busit-nz-public.zip", None),
    ("horizons-manawatu",
     "Connect / Horizons Regional Council",
     "Horizons Regional Council GTFS (Palmerston North, Manawatu-Whanganui)",
     "Manawatu-Whanganui", "Palmerston North",
     "https://www.horizons.govt.nz/HRC/media/Data/files/tranzit/HRC_GTFS_Production.zip", None),
    ("otago-regional-council",
     "Otago Regional Council (ORC)",
     "Otago Regional Council GTFS (Dunedin, Queenstown)",
     "Otago", "Dunedin",
     "https://www.orc.govt.nz/transit/google_transit.zip", None),
    ("metro-christchurch",
     "Metro Christchurch (Environment Canterbury)",
     "Metro Christchurch GTFS (Christchurch, Canterbury)",
     "Canterbury", "Christchurch",
     "https://apis.metroinfo.co.nz/rti/gtfs/v1/gtfs.zip", "CC-BY-4.0"),
]


def slugify(s):
    s = s.lower()
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


def fetch_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def is_nz_domain_url(url):
    """Only keep feeds whose producer zip is hosted on an NZ producer domain, so we
    never mis-attribute a shared vendor DMFR's foreign operators to NZ."""
    m = re.match(r"https?://([^/]+)", url or "")
    if not m:
        return False
    host = m.group(1).lower()
    # Accept *.nz hosts, and the known NZ council data blob host.
    if host.endswith(".nz"):
        return True
    if "wrcscheduledata.blob.core.windows.net" in host:  # Waikato RC (BUSIT)
        return True
    return False


def make_record(slug, provider, name, subdiv, city, producer_url, license_id):
    return {
        "id": CC.lower() + "-" + slug,
        "provider": provider,
        "name": name,
        "cc": CC,
        "subdiv": subdiv,
        "city": city,
        "producer_url": producer_url,
        "hosted_url": None,
        "license": license_id,
        "bbox": None,
        "status": "active",
        "official": True,
    }


def harvest_atlas():
    """Tier 1: parse NZ-domain DMFR files from the Transitland Atlas CDN."""
    recs = []
    for dom in NZ_DMFR_FILES:
        data = fetch_json(ATLAS_BASE + dom + ".dmfr.json")
        if not data:
            continue
        subdiv, city = DOMAIN_HINTS.get(dom, (None, None))
        for feed in data.get("feeds", []):
            if feed.get("spec") != "gtfs":
                continue
            url = (feed.get("urls") or {}).get("static_current")
            if not url or not isinstance(url, str):
                continue
            if not is_nz_domain_url(url):
                continue
            lic = (feed.get("license") or {}).get("spdx_identifier")
            ops = [o.get("name") for o in feed.get("operators", []) if o.get("name")]
            provider = ops[0] if ops else dom
            if len(ops) > 1:
                provider = ops[0] + " (+%d more)" % (len(ops) - 1)
            fid = feed.get("id") or slugify(dom)
            name = "GTFS — %s (%s)" % (provider, dom)
            recs.append(make_record(
                slugify(fid), provider, name, subdiv, city, url, lic))
    return recs


def main():
    existing = load_existing()
    seen = {r.get("producer_url", "").rstrip("/")
            for r in existing if isinstance(r, dict)}

    candidates = harvest_atlas()

    # Tier 2: union with the verified fallback list (covers CDN/network failure and
    # any NZ producer the atlas parse missed).
    have_urls = {c["producer_url"].rstrip("/") for c in candidates}
    for slug, provider, name, subdiv, city, url, lic in FALLBACK:
        if url.rstrip("/") in have_urls:
            continue
        candidates.append(make_record(slug, provider, name, subdiv, city, url, lic))
        have_urls.add(url.rstrip("/"))

    added = 0
    for rec in candidates:
        key = rec["producer_url"].rstrip("/")
        if not key or key in seen:
            continue
        existing.append(rec)
        seen.add(key)
        added += 1

    with open(SRC, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    print("+{n} new {cc} feeds".format(n=added, cc=CC))


if __name__ == "__main__":
    main()
