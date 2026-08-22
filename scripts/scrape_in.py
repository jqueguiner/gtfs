#!/usr/bin/env python3
"""
India (IN) GTFS feed scraper.

Landscape
---------
India has NO EU-style National Access Point and no single MoRTH GTFS portal.
The practical open-transit landscape is:

  * per-operator official portals: Delhi Open Transit Data (OTD), Kochi Metro
    (KMRL), Hyderabad Metro (HMRL);
  * community feeds (BMTC Bengaluru, PMPML Pune) generated from operator apps;
  * two enumerators that aggregate the above -- busmaps.com and Transitland.

Discovery strategy (robust, stdlib-only)
----------------------------------------
1. Transitland REST -- the licensing-clear, machine-enumerable aggregator.
   GET https://transit.land/api/v2/rest/feeds?adm0_iso=IN&apikey=KEY
   enumerating every India feed and reading urls.static_current (the direct
   GTFS zip), onestop_id and license. This needs a free key; supply it via
   the TRANSITLAND_APIKEY env var. When no key is present (or the call fails)
   the scraper silently skips this path -- it never hard-fails on it.

   NOTE on busmaps.com: its India catalog (busmaps.com/en/india) enumerates
   *regions* and *cities*, and the per-agency pages
   (/en/india/public_transit-agency-<Name>-<ids>?cityId=<id>) only expose a
   GTFS zip behind a free developer access token (/en/developers/access), so
   there is no key-free, machine-resolvable direct zip URL there. Transitland
   is therefore the enumerator we automate; busmaps is left as a manual
   fallback and is documented per operator below.

2. A curated seed of India operators whose direct open GTFS zip (or official
   portal landing) was verified reachable at authoring time. These cover the
   feeds that Transitland either gates behind a key or does not host directly.
   Each URL is probed at run time; a feed that is momentarily unreachable is
   still emitted (Indian feeds are intermittently down) but flagged in stdout.

Dedup is by producer_url (rstrip('/')), so a seed feed that Transitland also
returns under the same static URL is inserted only once. Each record has
EXACTLY these keys:
  id, provider, name, cc, subdiv, city, producer_url, hosted_url,
  license, bbox, status, official
"""

import json
import os
import re
import urllib.request

CC = "IN"
UA = "Mozilla/5.0 (compatible; gtfs-catalog/1.0; +https://github.com/jqueguiner/gtfs)"
TIMEOUT = 60

SRC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "feeds_full.json",
)

# ---------------------------------------------------------------------------
# Transitland REST enumeration (only runs when a key is available)
# ---------------------------------------------------------------------------
TL_APIKEY = os.environ.get("TRANSITLAND_APIKEY", "").strip()
TL_BASE = "https://transit.land/api/v2/rest/feeds"


def http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def url_reachable(url):
    """Best-effort HEAD-ish probe. GitHub-raw and portals answer to GET, so we
    open a ranged GET and only read the status line. Never raises."""
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": UA, "Range": "bytes=0-0"}
        )
        with urllib.request.urlopen(req, timeout=25) as r:
            return 200 <= getattr(r, "status", r.getcode()) < 400
    except Exception:
        return False


def slugify(s):
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "feed"


def tl_license(feed):
    """Map a Transitland feed.license object to a short label, or None."""
    lic = feed.get("license") or {}
    spdx = (lic.get("spdx_identifier") or "").strip()
    if spdx:
        return spdx
    url = (lic.get("url") or "").strip()
    if url:
        return url
    use = (lic.get("use_without_attribution") or "").strip()
    return use or None


def scrape_transitland():
    """Yield a feed record for every India feed Transitland exposes with a
    direct static GTFS url. No-op (with a note) when no key is configured."""
    if not TL_APIKEY:
        print("  transitland: no TRANSITLAND_APIKEY set, skipping REST enumeration")
        return
    url = "%s?adm0_iso=%s&limit=200&apikey=%s" % (TL_BASE, CC, TL_APIKEY)
    seen_page = set()
    while url:
        try:
            data = http_json(url)
        except Exception as e:
            print("  transitland fetch failed: %s" % e)
            return
        feeds = data.get("feeds") or []
        for feed in feeds:
            spec = (feed.get("spec") or "").lower()
            if spec and spec != "gtfs":
                continue
            urls = feed.get("urls") or {}
            static = (urls.get("static_current") or "").strip()
            if not static:
                latest = urls.get("static_historic") or []
                if isinstance(latest, list) and latest:
                    static = (latest[0] or "").strip()
            if not static or not static.lower().startswith("http"):
                continue
            osid = feed.get("onestop_id") or slugify(static)
            name = feed.get("name") or osid
            yield {
                "id": "%s-%s" % (CC.lower(), slugify(osid)),
                "provider": name,
                "name": "%s (Transitland %s)" % (name, osid),
                "cc": CC,
                "subdiv": None,
                "city": None,
                "producer_url": static,
                "hosted_url": None,
                "license": tl_license(feed),
                "bbox": None,
                "status": "active",
                "official": True,
            }
        # pagination
        meta = data.get("meta") or {}
        nxt = meta.get("next")
        if nxt and nxt not in seen_page:
            seen_page.add(nxt)
            url = nxt if "apikey=" in nxt else nxt + ("&" if "?" in nxt else "?") + "apikey=" + TL_APIKEY
        else:
            url = None


# ---------------------------------------------------------------------------
# Curated, verified India operator seeds
# ---------------------------------------------------------------------------
# Each: id-slug, provider, feed name, subdiv, city, producer_url, license.
# producer_url is the most direct open GTFS artifact (zip) available, or the
# official portal landing when the operator serves a .txt bundle / gated form.
SEEDS = [
    # Bengaluru -- BMTC community GTFS (built from Namma BMTC app), direct zip.
    {
        "slug": "bmtc-bengaluru",
        "provider": "Bengaluru Metropolitan Transport Corporation (BMTC)",
        "name": "BMTC Bengaluru bus GTFS (community, Vonter/bmtc-gtfs)",
        "subdiv": "Karnataka",
        "city": "Bengaluru",
        "producer_url": "https://raw.githubusercontent.com/Vonter/bmtc-gtfs/master/gtfs/bmtc.zip",
        "license": "MIT",
        "official": False,
    },
    # Pune -- PMPML community GTFS (from Apli-PMPML / Chartr API), direct zip.
    {
        "slug": "pmpml-pune",
        "provider": "Pune Mahanagar Parivahan Mahamandal Ltd (PMPML)",
        "name": "PMPML Pune bus GTFS (community, croyla/pmpml-gtfs)",
        "subdiv": "Maharashtra",
        "city": "Pune",
        "producer_url": "https://raw.githubusercontent.com/croyla/pmpml-gtfs/main/pmpml_gtfs.zip",
        "license": "MIT",
        "official": False,
    },
    # Kochi -- KMRL: first Indian metro to publish GTFS; integrated
    # metro + city bus + water-metro boat. Official open zip.
    {
        "slug": "kmrl-kochi",
        "provider": "Kochi Metro Rail Ltd (KMRL)",
        "name": "Kochi integrated GTFS -- metro + city bus + water metro (KMRL Open Data)",
        "subdiv": "Kerala",
        "city": "Kochi",
        "producer_url": "https://kochimetro.org/opendata/KMRLOpenData.zip",
        "license": "Free non-exclusive, attribution required (KMRL Open Data)",
        "official": True,
    },
    # Delhi -- OTD official portal (DTC/DIMTS buses). Static is a .txt bundle
    # off traffickarma + a Transitland-mirrored zip; the OTD /data/static page
    # is the stable official landing/producer entry point.
    {
        "slug": "otd-delhi-bus",
        "provider": "Delhi Integrated Multi-Modal Transit System (DIMTS) / DTC",
        "name": "Delhi OTD bus GTFS static (Open Transit Data, Delhi)",
        "subdiv": "Delhi",
        "city": "Delhi",
        "producer_url": "https://otd.delhi.gov.in/data/static/",
        "license": "opendata.iiitd.edu.in terms",
        "official": True,
    },
    # Delhi Metro (DMRC) via OTD staticDMRC section.
    {
        "slug": "otd-delhi-dmrc",
        "provider": "Delhi Metro Rail Corporation (DMRC)",
        "name": "Delhi Metro (DMRC) GTFS static (OTD staticDMRC)",
        "subdiv": "Delhi",
        "city": "Delhi",
        "producer_url": "https://otd.delhi.gov.in/data/staticDMRC/",
        "license": "opendata.iiitd.edu.in terms",
        "official": True,
    },
    # Hyderabad Metro (HMRL) -- open GTFS, download via Google Form; the
    # open-data page is the official producer landing.
    {
        "slug": "hmrl-hyderabad",
        "provider": "Hyderabad Metro Rail Ltd (HMRL)",
        "name": "Hyderabad Metro (HMRL) Open Data GTFS",
        "subdiv": "Telangana",
        "city": "Hyderabad",
        "producer_url": "https://hmrl.co.in/open-data/",
        "license": "Free non-exclusive (HMRL Open Data)",
        "official": True,
    },
    # Chennai MTC + CMRL -- Transitland-archived feed; the operator has no
    # key-free direct zip, so we point at the busmaps operator catalog page as
    # the discoverable producer entry (kept distinct from Transitland records).
    {
        "slug": "mtc-cmrl-chennai",
        "provider": "Metropolitan Transport Corporation (MTC) / Chennai Metro (CMRL)",
        "name": "Chennai MTC bus + CMRL metro GTFS (busmaps / Transitland)",
        "subdiv": "Tamil Nadu",
        "city": "Chennai",
        "producer_url": "https://busmaps.com/en/india/Chennai-MTC-CMRL/chennai-mtc-cmrl",
        "license": None,
        "official": False,
    },
]


def scrape_seeds():
    for s in SEEDS:
        pu = s["producer_url"].strip()
        ok = url_reachable(pu)
        if not ok:
            print("  seed unreachable (emitting anyway): %s" % pu)
        yield {
            "id": "%s-%s" % (CC.lower(), s["slug"]),
            "provider": s["provider"],
            "name": s["name"],
            "cc": CC,
            "subdiv": s.get("subdiv"),
            "city": s.get("city"),
            "producer_url": pu,
            "hosted_url": None,
            "license": s.get("license"),
            "bbox": None,
            "status": "active",
            "official": bool(s.get("official")),
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
    for rec in list(scrape_transitland()) + list(scrape_seeds()):
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
