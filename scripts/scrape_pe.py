#!/usr/bin/env python3
"""
Peru (PE) GTFS feed scraper.

Peru has NO legally-mandated National Access Point. datosabiertos.gob.pe has an
ATU group that publishes ZERO GTFS datasets, ATU (atu.gob.pe) publishes no open
feed, and Lima's historical GTFS was commercial (WhereIsMyTransport). The de-facto
OPEN aggregator is the Trufi Association GitHub org, which builds GTFS for
Peruvian cities from OSM/KML. This scraper pulls two open sources:

  1. Trufi Association GitHub org (github.com/orgs/trufi-association)
     GET https://api.github.com/orgs/trufi-association/repos?per_page=100 (paginate)
     For each repo, GET .../git/trees/HEAD?recursive=1 and scan tree[].path for
     a built feed  '.../out/gtfs.zip'  (download directly) or a raw feed folder
     '.../out/gtfs/' that contains agency.txt+stops.txt+routes.txt+trips.txt
     (the individual .txt files are the feed; there is no zip -- e.g. Arequipa).
     Only PERU repos are kept: the GTFS path must contain a Peru marker
     ('peru' / a known Peru city) so Bolivian/Colombian/etc Trufi repos are
     excluded (quirqui-rutas = Oruro-Bolivia, trufi-app = Cochabamba, ...).

  2. Mobility Database (MobilityData/mobility-database-catalogs) Peru sources.
     GET https://api.github.com/repos/MobilityData/mobility-database-catalogs/git/trees/main?recursive=1
     grep tree paths for 'sources/gtfs/schedule/pe-', then read each source JSON's
     urls.direct_download. (MDB catalogs exactly 2 PE feeds: Aeroexpreso #1985 &
     Trujillo #2200; the Trujillo one mirrors the Trufi repo -> deduped.)

The GitHub REST API rate-limits anonymous callers to 60 req/hr; if a
GITHUB_TOKEN / GH_TOKEN env var is present it is used (Bearer) for api.github.com
calls to lift the cap. raw.githubusercontent.com and the MDB source JSONs need
no auth.

Each record appended to data/feeds_full.json has EXACTLY these keys:
  id, provider, name, cc, subdiv, city, producer_url, hosted_url,
  license, bbox, status, official
Dedup is by producer_url (rstrip('/'), with GitHub 'refs/heads/<b>' normalised
to '<b>'). Stdlib only (json, urllib, os, re).
"""

import json
import os
import re
import urllib.request
import urllib.error

CC = "PE"
UA = "Mozilla/5.0 (compatible; gtfs-catalog/1.0; +https://github.com/jqueguiner/gtfs)"
TIMEOUT = 60

SRC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "feeds_full.json",
)

GH_API = "https://api.github.com"
TRUFI_ORG = "trufi-association"
RAW_BASE = "https://raw.githubusercontent.com"
MDB_REPO = "MobilityData/mobility-database-catalogs"
MDB_RAW = RAW_BASE + "/MobilityData/mobility-database-catalogs/main/%s"

# Peru markers used to keep only Peruvian Trufi repos/feeds. Maps a marker found
# in the GTFS path to (city, subdiv) metadata; 'peru' is a generic fallback.
PE_CITIES = {
    "trujillo": ("Trujillo", "La Libertad"),
    "arequipa": ("Arequipa", "Arequipa"),
    "lima": ("Lima / Callao", "Lima"),
    "callao": ("Lima / Callao", "Callao"),
    "cusco": ("Cusco", "Cusco"),
    "cuzco": ("Cusco", "Cusco"),
    "chiclayo": ("Chiclayo", "Lambayeque"),
    "piura": ("Piura", "Piura"),
    "iquitos": ("Iquitos", "Loreto"),
    "huancayo": ("Huancayo", "Junin"),
    "tacna": ("Tacna", "Tacna"),
}
REQUIRED_RAW = ("agency.txt", "stops.txt", "routes.txt", "trips.txt")


def http_bytes(url, accept=None):
    headers = {"User-Agent": UA}
    if accept:
        headers["Accept"] = accept
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if tok and url.startswith(GH_API):
        headers["Authorization"] = "Bearer " + tok
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def http_json(url):
    return json.loads(
        http_bytes(url, accept="application/vnd.github+json").decode("utf-8", "replace")
    )


def url_ok(url):
    """True on HTTP 2xx for a plain GET; used to verify a feed URL is reachable."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA}, method="GET")
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return 200 <= r.status < 300
    except Exception:
        return False


def norm_url(u):
    """Canonicalise a producer_url for dedup: strip trailing '/', collapse the
    GitHub raw 'refs/heads/<branch>' form to just '<branch>' so the same file
    referenced two ways (MDB uses refs/heads/main, Trufi uses main) dedups."""
    u = (u or "").rstrip("/")
    u = re.sub(r"(raw\.githubusercontent\.com/[^/]+/[^/]+)/refs/heads/", r"\1/", u)
    return u


def slugify(s):
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "feed"


def spdx(lic):
    """Normalise a GitHub license object / spdx id to a clean label or None."""
    if isinstance(lic, dict):
        lic = lic.get("spdx_id")
    if not lic or lic in ("NOASSERTION", "NONE"):
        return None
    return lic


def pe_marker(path):
    """Return (city, subdiv) if a Peru marker appears in the path, else None.

    'peru' anywhere (e.g. 'GTFS-Peru-Trujillo') qualifies; a bare city name only
    qualifies alongside a peru/pe context to avoid false positives.
    """
    low = path.lower()
    is_peru = "peru" in low or "-pe-" in low or low.startswith("pe-")
    hit = None
    for marker, meta in PE_CITIES.items():
        if re.search(r"(^|[^a-z])%s([^a-z]|$)" % marker, low):
            hit = meta
            break
    if is_peru:
        return hit or (None, None)
    return None


def list_trufi_repos():
    repos = []
    page = 1
    while page <= 20:
        url = "%s/orgs/%s/repos?per_page=100&page=%d" % (GH_API, TRUFI_ORG, page)
        try:
            batch = http_json(url)
        except Exception as e:
            print("  trufi repo list page %d failed: %s" % (page, e))
            break
        if not isinstance(batch, list) or not batch:
            break
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return repos


def scrape_trufi():
    """Yield PE feed records discovered in the Trufi Association GitHub org."""
    for repo in list_trufi_repos():
        if repo.get("fork"):
            continue
        name = repo.get("name")
        branch = repo.get("default_branch") or "HEAD"
        lic = spdx(repo.get("license"))
        try:
            tree = http_json(
                "%s/repos/%s/%s/git/trees/%s?recursive=1"
                % (GH_API, TRUFI_ORG, name, branch)
            )
        except Exception as e:
            print("  tree fetch failed for %s: %s" % (name, e))
            continue
        # Skip the builder's own bundled fixtures (examples/, test data) --
        # they are sample outputs of the GTFS builder, not city feeds.
        paths = [
            t.get("path", "")
            for t in (tree.get("tree") or [])
            if not re.match(
                r"(^|.*/)(examples?|tests?|fixtures?|sample)s?/", t.get("path", "")
            )
        ]

        # 1) Built feeds: any '.../out/gtfs.zip' under a Peru path.
        zip_dirs = set()  # '.../out/gtfs' dirs that already have a built zip
        for p in paths:
            if not p.endswith("/out/gtfs.zip") and p != "out/gtfs.zip":
                continue
            meta = pe_marker(p) or pe_marker(name)
            if meta is None:
                continue
            zip_dirs.add(p[: -len("gtfs.zip")] + "gtfs")  # '.../out/gtfs'
            city, subdiv = meta
            zurl = "%s/%s/%s/%s/%s" % (RAW_BASE, TRUFI_ORG, name, branch, p)
            rec = _mk(name, city, subdiv, zurl, lic, city or name, kind="zip")
            if rec:
                yield rec

        # 2) Raw feeds: a '.../out/gtfs/' folder holding the required txt files.
        #    Group tree paths by their gtfs dir; require agency/stops/routes/trips.
        #    Skip any folder whose sibling gtfs.zip was already emitted (the built
        #    zip is the canonical feed for that city).
        dirs = {}
        for p in paths:
            m = re.match(r"(.*?/out/gtfs)/([^/]+\.txt)$", p) or re.match(
                r"^(out/gtfs)/([^/]+\.txt)$", p
            )
            if m:
                dirs.setdefault(m.group(1), set()).add(m.group(2))
        for gdir, files in dirs.items():
            if gdir in zip_dirs:
                continue
            if not set(REQUIRED_RAW) <= files:  # subset check
                continue
            meta = pe_marker(gdir) or pe_marker(name)
            if meta is None:
                continue
            city, subdiv = meta
            # No zip exists -> producer_url is the raw GTFS folder base (the
            # aggregator-exposed feed location; a consumer fetches the .txt set).
            folder = "%s/%s/%s/%s/%s/" % (RAW_BASE, TRUFI_ORG, name, branch, gdir)
            rec = _mk(name, city, subdiv, folder, lic, city or name, kind="raw")
            if rec:
                yield rec


def _mk(repo, city, subdiv, producer_url, lic, title_city, kind):
    """Build one record; verify the URL is reachable before emitting."""
    probe = producer_url if kind == "zip" else producer_url + "agency.txt"
    if not url_ok(probe):
        print("  skip unreachable %s (%s)" % (producer_url, repo))
        return None
    provider = "Trufi Association -- %s (built from OSM/KML)" % (title_city or repo)
    name = "%s GTFS (Trufi Association, OSM-derived)%s" % (
        title_city or repo,
        "" if kind == "zip" else " [raw txt]",
    )
    return {
        "id": "%s-%s" % (CC.lower(), slugify(repo)),
        "provider": provider,
        "name": name,
        "cc": CC,
        "subdiv": subdiv,
        "city": city,
        "producer_url": producer_url,
        "hosted_url": None,
        "license": lic,
        "bbox": None,
        "status": "active",
        "official": True,
    }


def scrape_mdb():
    """Yield PE feed records from the Mobility Database catalog."""
    try:
        tree = http_json("%s/repos/%s/git/trees/main?recursive=1" % (GH_API, MDB_REPO))
    except Exception as e:
        print("  MDB tree fetch failed: %s" % e)
        return
    files = [
        t.get("path", "")
        for t in (tree.get("tree") or [])
        if re.search(r"sources/gtfs/schedule/pe-.*\.json$", t.get("path", ""))
    ]
    for path in files:
        try:
            src = json.loads(http_bytes(MDB_RAW % path).decode("utf-8", "replace"))
        except Exception as e:
            print("  MDB source fetch failed (%s): %s" % (path, e))
            continue
        urls = src.get("urls") or {}
        direct = (urls.get("direct_download") or "").strip()
        if not direct:
            continue
        loc = src.get("location") or {}
        subdiv = loc.get("subdivision_name")
        muni = loc.get("municipality")
        provider = src.get("provider") or "Peru operator"
        stem = re.sub(r"\.json$", "", os.path.basename(path))
        yield {
            "id": "%s-%s" % (CC.lower(), slugify(stem)),
            "provider": provider,
            "name": "%s GTFS (Mobility Database)" % provider,
            "cc": CC,
            "subdiv": subdiv,
            "city": muni or subdiv,
            "producer_url": direct,
            "hosted_url": None,
            "license": (urls.get("license") or None),
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
        pu = norm_url(rec.get("producer_url"))
        if pu:
            have.add(pu)

    added = []
    seen_new = set()
    for rec in list(scrape_trufi()) + list(scrape_mdb()):
        pu = norm_url(rec.get("producer_url"))
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
