#!/usr/bin/env python3
"""Scraper for Romania (RO) open-transit GTFS feeds.

Romania has NO working legally-mandated National Access Point (unlike FR/DE/NO).
Open GTFS is fragmented across several de-facto aggregators/hosts:

  (1) TPBI (Transport Public Bucuresti-Ilfov) official open-data portal
        https://gtfs.tpbi.ro/regional/
      Serves a single unified regional feed (STB, STV, Metrorex, Ecotrans/STCM,
      Regio Serv) + an STB-only feed as plain application/zip. Directory listing
      is scrapable; we parse the <a href="*.zip"> links.

  (2) external.gtfs.ro  -- a plain nginx directory-listing host serving per-city
      GTFS zips at https://external.gtfs.ro/<city>/<CITY>.zip. Each city dir is
      an Apache/nginx autoindex; we GET the dir and parse the <a href="*.zip">.
      Verified live (HTTP 200): /constanta/, /oradea/. Some dirs (cluj, iasi,
      craiova) return 403 (key/referer-gated) and are skipped on failure. The
      root itself is NOT an index, so we probe a fixed candidate slug list.

  (3) tursib.ro (Sibiu) -- official direct GTFS. https://www.tursib.ro/trasee/gtfs
      301-redirects to a versioned zip; we follow redirects to the final URL.

  (4) tranzy.ai Open Data REST API (CTP Cluj, SCTP Iasi, STPT Timisoara,
      Botosani) -- GTFS-shaped JSON, NOT a bulk zip, and every endpoint returns
      403 without a free X-API-KEY (verified against the live openapi.json:
      /agency, /routes, /stops ... all 403). We cannot enumerate agencies or
      emit a direct producer zip URL without a key, so these operators are not
      appended here (the schema requires a direct GTFS zip in producer_url).

Only records with a real, resolvable direct GTFS zip URL are appended. Dedup is
by producer_url (rstrip('/')). stdlib only. Appends to data/feeds_full.json.
"""
import json
import os
import re
import urllib.request
import urllib.error

CC = "RO"
UA = "Mozilla/5.0 (compatible; gtfs-catalog-scraper/1.0)"
TIMEOUT = 40

SRC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "feeds_full.json",
)

EXT_BASE = "https://external.gtfs.ro"
TPBI_DIR = "https://gtfs.tpbi.ro/regional/"
HREF_RE = re.compile(r'href\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)

# external.gtfs.ro per-city directories to probe. Only those returning 200 with
# a parseable *.zip href are appended; 403/404 are skipped. A per-city Referer
# (operator site) is sent in case the host referer-gates a listing.
EXT_CITIES = {
    "constanta": {
        "provider": "CT Bus",
        "subdiv": "Constanta",
        "city": "Constanta",
        "referer": "https://www.ctbus.ro/",
    },
    "oradea": {
        "provider": "OTL (Oradea Transport Local)",
        "subdiv": "Bihor",
        "city": "Oradea",
        "referer": "https://otlra.ro/",
    },
    "cluj": {
        "provider": "CTP Cluj-Napoca",
        "subdiv": "Cluj",
        "city": "Cluj-Napoca",
        "referer": "https://ctpcj.ro/",
    },
    "iasi": {
        "provider": "SCTP Iasi",
        "subdiv": "Iasi",
        "city": "Iasi",
        "referer": "https://www.sctpiasi.ro/",
    },
    "craiova": {
        "provider": "RAT Craiova",
        "subdiv": "Dolj",
        "city": "Craiova",
        "referer": "https://www.ratcraiova.ro/",
    },
    "timisoara": {
        "provider": "STPT (Societatea de Transport Public Timisoara)",
        "subdiv": "Timis",
        "city": "Timisoara",
        "referer": "https://stpt.ro/",
    },
    "brasov": {
        "provider": "RATBV (Regia Autonoma de Transport Brasov)",
        "subdiv": "Brasov",
        "city": "Brasov",
        "referer": "https://www.ratbv.ro/",
    },
    "sibiu": {
        "provider": "Tursib",
        "subdiv": "Sibiu",
        "city": "Sibiu",
        "referer": "https://www.tursib.ro/",
    },
    "ploiesti": {
        "provider": "TCE Ploiesti (Transport Calatori Express)",
        "subdiv": "Prahova",
        "city": "Ploiesti",
        "referer": "https://ratph.ro/",
    },
    "galati": {
        "provider": "Transurb Galati",
        "subdiv": "Galati",
        "city": "Galati",
        "referer": "https://www.transurbgalati.ro/",
    },
    "arad": {
        "provider": "CTP Arad",
        "subdiv": "Arad",
        "city": "Arad",
        "referer": "https://ctparad.ro/",
    },
    "botosani": {
        "provider": "Eltrans Botosani",
        "subdiv": "Botosani",
        "city": "Botosani",
        "referer": "https://www.eltrans.ro/",
    },
    "targumures": {
        "provider": "Transport Local Targu Mures",
        "subdiv": "Mures",
        "city": "Targu Mures",
        "referer": "https://transportlocal.ro/",
    },
}

# Fixed, verified direct GTFS zips (no key, application/zip HTTP 200).
DIRECT_FEEDS = [
    {
        "slug": "tpbi-bucharest-region",
        "provider": "TPBI (STB, STV, Metrorex, Ecotrans/STCM, Regio Serv)",
        "name": "TPBI Regional GTFS - Bucharest + Ilfov (unified, incl. Metrorex)",
        "subdiv": "Bucuresti-Ilfov",
        "city": "Bucharest",
        "producer_url": "https://gtfs.tpbi.ro/regional/BUCHAREST-REGION.zip",
        "license": None,
    },
    {
        "slug": "tpbi-stb",
        "provider": "STB (Societatea de Transport Bucuresti)",
        "name": "STB GTFS - Bucharest surface transport (bus/tram/trolleybus)",
        "subdiv": "Bucuresti-Ilfov",
        "city": "Bucharest",
        "producer_url": "https://gtfs.tpbi.ro/regional/STB.zip",
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


def http_get(url, referer=None):
    """GET url, following redirects. Returns (final_url, content_type, body_bytes)."""
    headers = {"User-Agent": UA, "Accept": "*/*"}
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        final_url = resp.geturl()
        ctype = (resp.headers.get("Content-Type") or "").lower()
        body = resp.read()
    return final_url, ctype, body


def head_ok(url, referer=None):
    """Return the final resolved URL if url resolves (HTTP 200), else None."""
    headers = {"User-Agent": UA, "Accept": "*/*"}
    if referer:
        headers["Referer"] = referer
    try:
        req = urllib.request.Request(url, headers=headers, method="HEAD")
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            if resp.status == 200:
                return resp.geturl()
    except urllib.error.HTTPError:
        return None
    except Exception:
        return None
    return None


def parse_dir_zips(base_url, html):
    """From a directory-listing HTML, return absolute URLs of *.zip hrefs."""
    out = []
    for href in HREF_RE.findall(html):
        h = href.strip()
        if not h.lower().endswith(".zip"):
            continue
        if h.startswith("http://") or h.startswith("https://"):
            out.append(h)
        else:
            out.append(base_url.rstrip("/") + "/" + h.lstrip("/"))
    return out


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


def collect_tpbi():
    """Parse the TPBI regional directory for *.zip feeds (dynamic + fixed)."""
    records = []
    try:
        _, _, body = http_get(TPBI_DIR)
        html = body.decode("utf-8", "replace")
        for zurl in parse_dir_zips(TPBI_DIR, html):
            fname = zurl.rsplit("/", 1)[-1]
            base = re.sub(r"\.zip$", "", fname, flags=re.IGNORECASE)
            # skip timetable/archive artifacts that are not full GTFS feeds
            if re.search(r"timetable", base, re.IGNORECASE):
                continue
            if re.match(r"^\d{6}-", base):  # dated archive snapshots
                continue
            up = base.upper()
            if up == "BUCHAREST-REGION":
                continue  # covered by fixed DIRECT_FEEDS
            if up == "STB":
                continue  # covered by fixed DIRECT_FEEDS
            records.append(
                rec(
                    slug="tpbi-" + slugify(base),
                    provider="TPBI ({})".format(base),
                    name="TPBI GTFS - {} (Bucharest-Ilfov region)".format(base),
                    subdiv="Bucuresti-Ilfov",
                    city="Bucharest",
                    producer_url=zurl,
                )
            )
    except Exception as e:
        print("WARN: TPBI dir fetch failed: {}".format(e))
    return records


def collect_external():
    """Probe each external.gtfs.ro city dir and parse its zip href."""
    records = []
    for city_slug, meta in EXT_CITIES.items():
        dir_url = "{}/{}/".format(EXT_BASE, city_slug)
        try:
            final_url, ctype, body = http_get(dir_url, referer=meta.get("referer"))
        except urllib.error.HTTPError as e:
            print("WARN: external.gtfs.ro/{} -> HTTP {} (skip)".format(city_slug, e.code))
            continue
        except Exception as e:
            print("WARN: external.gtfs.ro/{} -> {} (skip)".format(city_slug, e))
            continue

        zurls = []
        if "html" in ctype or "text" in ctype:
            zurls = parse_dir_zips(dir_url, body.decode("utf-8", "replace"))
        # Fallback: conventional <CITY>.zip if the dir did not autoindex a link.
        if not zurls:
            guess = "{}{}.zip".format(dir_url, city_slug.upper())
            resolved = head_ok(guess, referer=meta.get("referer"))
            if resolved:
                zurls = [guess]
        if not zurls:
            print("WARN: external.gtfs.ro/{} -> no zip found (skip)".format(city_slug))
            continue

        # take the first plausible zip (city dirs host a single feed zip)
        zurl = zurls[0]
        records.append(
            rec(
                slug=slugify(city_slug),
                provider=meta["provider"],
                name="{} GTFS ({}) - via external.gtfs.ro".format(
                    meta["provider"], meta["city"]
                ),
                subdiv=meta["subdiv"],
                city=meta["city"],
                producer_url=zurl,
            )
        )
    return records


def collect_tursib():
    """Follow the tursib.ro/trasee/gtfs redirect to the versioned zip URL."""
    url = "https://www.tursib.ro/trasee/gtfs"
    try:
        final_url, ctype, _ = http_get(url, referer="https://www.tursib.ro/")
    except Exception as e:
        print("WARN: tursib fetch failed: {}".format(e))
        return []
    if "zip" not in ctype and not final_url.lower().endswith(".zip"):
        print("WARN: tursib did not resolve to a zip ({})".format(ctype))
        return []
    return [
        rec(
            slug="tursib-sibiu",
            provider="Tursib",
            name="Tursib GTFS - Sibiu (official)",
            subdiv="Sibiu",
            city="Sibiu",
            producer_url=final_url,
        )
    ]


def main():
    existing = load_existing()
    seen = set()
    for r in existing:
        pu = r.get("producer_url")
        if pu:
            seen.add(pu.rstrip("/"))

    candidates = []
    # Fixed, verified direct feeds first.
    for d in DIRECT_FEEDS:
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
    # Dynamic sources.
    candidates.extend(collect_tpbi())
    candidates.extend(collect_external())
    candidates.extend(collect_tursib())

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
