#!/usr/bin/env python3
"""
Uruguay (UY) GTFS feed scraper.

Source
------
Catálogo Nacional de Datos Abiertos (catalogodatos.gub.uy), a CKAN portal.
The MTOP / Dirección Nacional de Transporte (DNT) publishes ONE dataset,
'Horarios de omnibus en líneas interdepartamentales', whose resource
'Horarios Metropolitanos GTFS' is a single valid multi-operator GTFS zip
covering the Montevideo metropolitan area + interdepartmental services for
8 operators (CUTCSA, COETC, UCOT, COME, COPSA, CITA, CASANOVA, TALA-PANDO-
MONTEVIDEO). This is Uruguay's canonical open GTFS.

Discovery is done via the CKAN action API, NOT by hardcoding the zip name:
the download filename is date-stamped (gtfs_YYYYMMDD.zip) and changes on every
update, so the live URL MUST be resolved from result.resources[] at run time.

  1. package_show?id=<the MTOP/DNT dataset>  -> the canonical national GTFS zip.
  2. package_search?q=GTFS&rows=100          -> any other GTFS resources exposed
                                                by the portal (future-proofing).

The aggregator exposes exactly ONE GTFS download (one producer_url) that
bundles all 8 operators (split internally by agency_id in agency.txt), so we
emit ONE canonical national multi-operator feed record — emitting 8 records
pointing at the identical zip would be pure duplication that the producer_url
dedup rule is meant to reject. The 8 in-feed operators are documented below for
reference. Montevideo IM's own CKAN (ckan.montevideo.gub.uy) publishes STM
ridership/shapefiles, not a standalone GTFS, so it is intentionally not treated
as a GTFS source. Maldonado / Punta del Este urban operators (CODESA, Maldonado
Turismo, Micro Ltda.) have no open GTFS and are excluded.

Each record appended to data/feeds_full.json has EXACTLY these keys:
  id, provider, name, cc, subdiv, city, producer_url, hosted_url,
  license, bbox, status, official
Dedup is by producer_url (rstrip('/')). Stdlib only.
"""

import json
import os
import re
import urllib.request

CC = "UY"
UA = "Mozilla/5.0 (compatible; gtfs-catalog/1.0; +https://github.com/jqueguiner/gtfs)"
TIMEOUT = 60

SRC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "feeds_full.json",
)

CKAN_BASE = "https://catalogodatos.gub.uy"
DATASET_ID = (
    "ministerio-de-transporte-y-obras-publicas-"
    "horarios-de-omnibus-en-lineas-interdepartamentales"
)
PACKAGE_SHOW = "%s/api/3/action/package_show?id=%s" % (CKAN_BASE, DATASET_ID)
PACKAGE_SEARCH = "%s/api/3/action/package_search?q=GTFS&rows=100" % CKAN_BASE

# CKAN license_id -> human/SPDX-ish label. The MTOP dataset uses odc-uy
# ("Licencia de Datos Abiertos de Gobierno del Uruguay"), which has no SPDX id.
LICENSE_MAP = {
    "odc-uy": "Licencia de Datos Abiertos de Gobierno de Uruguay",
    "cc-by": "CC-BY-4.0",
    "cc-zero": "CC0-1.0",
    "cc-by-sa": "CC-BY-SA-4.0",
    "odc-by": "ODC-BY-1.0",
    "odc-odbl": "ODbL-1.0",
    "notspecified": None,
    "": None,
    None: None,
}

# The 8 operators bundled inside the single national GTFS zip (agency_id in
# agency.txt). Kept for reference / provenance only — they are NOT emitted as
# separate records because they share the one national producer_url.
IN_FEED_OPERATORS = (
    "CUTCSA (50), COETC (10), UCOT (70), COME (20), "
    "TALA-PANDO-MONTEVIDEO/TPM (35), COPSA (18), CITA (29), CASANOVA (13)"
)


def http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def slugify(s):
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "feed"


def license_label(pkg):
    lid = (pkg.get("license_id") or "").lower()
    if lid in LICENSE_MAP:
        return LICENSE_MAP[lid]
    return pkg.get("license_title") or None


def is_gtfs_resource(res):
    """True if a CKAN resource looks like a direct GTFS zip download.

    The portal tags the format loosely (often 'ZIP', not 'GTFS'), so accept a
    .zip whose name/url signals GTFS, or an explicit GTFS format.
    """
    url = (res.get("url") or "").strip()
    if not url:
        return False
    fmt = (res.get("format") or "").lower()
    name = (res.get("name") or "").lower()
    low = url.lower()
    if fmt == "gtfs":
        return low.endswith(".zip") or "gtfs" in low
    if not low.endswith(".zip"):
        return False
    return "gtfs" in name or "gtfs" in low


def find_gtfs_url(pkg):
    """Return the live GTFS zip url from a CKAN package, or None."""
    for res in pkg.get("resources", []) or []:
        if is_gtfs_resource(res):
            return res["url"].strip()
    return None


def scrape_national():
    """Resolve the canonical national GTFS zip and emit the single national
    multi-operator feed record."""
    try:
        data = http_json(PACKAGE_SHOW)
    except Exception as e:
        print("  package_show fetch failed: %s" % e)
        return
    pkg = data.get("result") or {}
    zurl = find_gtfs_url(pkg)
    if not zurl:
        print("  no GTFS resource found in %s" % DATASET_ID)
        return
    yield {
        "id": "%s-mtop-dnt-gtfs" % CC.lower(),
        "provider": "MTOP / Dirección Nacional de Transporte (DNT)",
        "name": "Horarios Metropolitanos GTFS — Uruguay national "
                "(multi-operator: %s)" % IN_FEED_OPERATORS,
        "cc": CC,
        "subdiv": None,
        "city": "Montevideo",
        "producer_url": zurl,
        "hosted_url": None,
        "license": license_label(pkg),
        "bbox": None,
        "status": "active",
        "official": True,
    }


def scrape_search():
    """Discover any other GTFS resources exposed by the portal."""
    try:
        data = http_json(PACKAGE_SEARCH)
    except Exception as e:
        print("  package_search fetch failed: %s" % e)
        return
    for pkg in (data.get("result") or {}).get("results", []) or []:
        zurl = find_gtfs_url(pkg)
        if not zurl:
            continue
        name_ds = pkg.get("name") or pkg.get("id")
        title = pkg.get("title") or name_ds
        org = (pkg.get("organization") or {}).get("title")
        yield {
            "id": "%s-%s" % (CC.lower(), slugify(name_ds)),
            "provider": org or title,
            "name": title,
            "cc": CC,
            "subdiv": None,
            "city": None,
            "producer_url": zurl,
            "hosted_url": None,
            "license": license_label(pkg),
            "bbox": None,
            "status": "active",
            "official": True,
        }


def main():
    try:
        with open(SRC, "r", encoding="utf-8") as fh:
            existing = json.load(fh)
        if not isinstance(existing, list):
            existing = []
    except (FileNotFoundError, ValueError):
        existing = []

    have = set()
    for rec in existing:
        pu = (rec.get("producer_url") or "").rstrip("/")
        if pu:
            have.add(pu)

    added = []
    seen_new = set()
    for rec in list(scrape_national()) + list(scrape_search()):
        pu = (rec.get("producer_url") or "").rstrip("/")
        if not pu or pu in have or pu in seen_new:
            continue
        seen_new.add(pu)
        added.append(rec)

    if added:
        existing.extend(added)
        os.makedirs(os.path.dirname(SRC), exist_ok=True)
        with open(SRC, "w", encoding="utf-8") as fh:
            json.dump(existing, fh, ensure_ascii=False, indent=2)

    print("+%d new %s feeds" % (len(added), CC))


if __name__ == "__main__":
    main()
