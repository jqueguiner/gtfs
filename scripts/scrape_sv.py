#!/usr/bin/env python3
"""
El Salvador (SV) transit feed scraper.

Aggregator landscape
--------------------
El Salvador has NO GTFS feed, NO NeTEx, and NO EU-style legally-mandated
National Access Point. It is present in neither the Mobility Database nor
Transitland (both confirmed empty for SV as of 2026-08).

The *de-facto* national access point is the ArcGIS Online organization of the
Viceministerio de Transporte (VMT) -- org id 4ZwMO9wShTnUDuWy on
services9.arcgis.com. The VMT publishes the ENTIRE national bus network as
ArcGIS REST FeatureServices. The services directory lists ~655 FeatureServers,
of which 295 are individual bus routes:

  * AB*  -> Autobus  (191 routes)
  * MB*  -> Microbus (104 routes)

The other ~360 services are accident / signage / admin layers
(ACCIDENTES*, Base*Fallecidos*, Alcaldias*, RAP_*, etc.) -- skipped.

Each bus-route service has a polyline layer named {CODE}_RECORRIDO (route
geometry) and, for many routes, an extra {CODE}_PARADAS point layer (stops).
The RECORRIDO layer carries the schedule/fare attributes:
  NAME, TIPO_RUTA, RECORRIDO, H_INIC_LV, H_FIN_LV, H_INIC_SD, H_FIN_SD
  (service hours weekday / Sat-Sun), ORIGEN, DESTINO (municipality codes),
  TARIFA_AUT (fare USD), KILOMETROS, CODIGO_RUTA, TARIFA_EXCLU, TIPO_UNIDAD.

There is NO native stops.txt / stop_times.txt as a bulk GTFS, and NO GTFS zip
exists anywhere -- a consumer must synthesize GTFS from the REST attributes +
polyline geometry (+ the PARADAS layer where present). Because there is no
downloadable zip, the stable per-feed source URL we record as producer_url is
each route's ArcGIS REST FeatureServer endpoint -- the direct, authoritative,
queryable source for that route's geometry + schedule attributes. This mirrors
how other no-zip / API-keyed producers are recorded in this catalog.

Source
------
1. GET  https://services9.arcgis.com/4ZwMO9wShTnUDuWy/ArcGIS/rest/services?f=json
     -> response.services[] = [{name, type, url}, ...]
     Keep entries whose name matches ^(AB|MB)\\d and type == FeatureServer.
2. One catalog record per route FeatureServer (295 expected). No per-route
     network calls are required to build the record -- the service listing
     already gives the stable endpoint URL and route code -- so the scrape is
     fast and robust even when individual route layers are momentarily down.

Each record appended to data/feeds_full.json has EXACTLY these keys:
  id, provider, name, cc, subdiv, city, producer_url, hosted_url,
  license, bbox, status, official
Dedup is by producer_url (rstrip('/')). Stdlib only (json, urllib, os, re).
"""

import json
import os
import re
import urllib.request

CC = "SV"
UA = "Mozilla/5.0 (compatible; gtfs-catalog/1.0; +https://github.com/jqueguiner/gtfs)"

# VMT ArcGIS Online organization (de-facto national access point).
ORG_ID = "4ZwMO9wShTnUDuWy"
SERVICES_DIR = (
    "https://services9.arcgis.com/%s/ArcGIS/rest/services?f=json" % ORG_ID
)

PROVIDER = "Viceministerio de Transporte (VMT)"
LICENSE = None  # No explicit open licence published on the VMT ArcGIS org.

# Bus-route service naming: AB###... (Autobus) / MB###... (Microbus).
ROUTE_RE = re.compile(r"^(AB|MB)\d")

SRC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "feeds_full.json",
)


def http_get_json(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def slugify(s):
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def scrape_services():
    """Yield one catalog record per VMT bus-route FeatureService."""
    try:
        data = http_get_json(SERVICES_DIR)
    except Exception as e:
        print("  VMT services directory unreachable: %s" % e)
        return

    services = data.get("services") or []
    if not isinstance(services, list):
        print("  unexpected services payload shape")
        return

    for svc in services:
        try:
            name = (svc.get("name") or "").strip()
            stype = (svc.get("type") or "").strip()
            if stype != "FeatureServer":
                continue
            if not ROUTE_RE.match(name):
                continue

            url = (svc.get("url") or "").strip()
            if not url:
                url = (
                    "https://services9.arcgis.com/%s/ArcGIS/rest/services/"
                    "%s/FeatureServer" % (ORG_ID, name)
                )
            # Normalise to the FeatureServer root (queryable endpoint).
            url = url.rstrip("/")

            kind = "Autobus" if name.startswith("AB") else "Microbus"
            title = (
                "VMT bus route %s (%s) - ArcGIS REST FeatureServer "
                "[route geometry + schedule/fare attributes; synthesize GTFS]"
                % (name, kind)
            )

            yield {
                "id": "%s-%s" % (CC.lower(), slugify(name)),
                "provider": PROVIDER,
                "name": title,
                "cc": CC,
                "subdiv": None,
                "city": None,
                "producer_url": url,
                "hosted_url": None,
                "license": LICENSE,
                "bbox": None,
                "status": "active",
                "official": True,
            }
        except Exception as e:
            print("  skipping malformed service entry: %s" % e)
            continue


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
    for rec in scrape_services():
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
