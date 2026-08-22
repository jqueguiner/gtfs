#!/usr/bin/env python3
"""Scraper for Lithuania (LT) GTFS feeds via Visimarsrutai, the national NAP.

Visimarsrutai (visimarsrutai.lt/gtfs) is the de-facto Lithuanian National Access
Point for scheduled public transport. The directory hosts one GTFS zip per
municipality/region authority (~56 "savivaldybe" feeds) plus LTSAR.zip (rail /
national coach registry curated by LTSA), and two aggregate builds:
  - gtfs_all.zip      : raw bulk merge of every authority (~66MB)
  - google_transit.zip: Google-Transit-formatted national aggregate (~60MB)

Machine-readable index: https://www.visimarsrutai.lt/gtfs/export-report.json
  {
    "googleAllInfo": { fileUrl?, jobStatus, routesCount, agenciesCount, ... },
    "authorityInfo": [
      { "fileUrl": "https://www.visimarsrutai.lt/gtfs/KaunoM.zip",
        "fileName": "KaunoM.zip", "agencyId": 62, "agencyName": "Kauno m. sav.",
        "routesCount": 83, "firstService": "2024-02-03",
        "lastService": "2027-08-21", "jobStatus": "COMPLETED",
        "validationResult": "https://.../KaunoM.zip-validation-report.html" },
      ...
    ]
  }

Strategy: parse the JSON index, iterate authorityInfo[], skip any entry whose
jobStatus is not a success state (COMPLETED/SUCCESS), and emit one feed per
authority using entry.fileUrl as the direct producer_url. We also emit the
national google_transit.zip aggregate. This yields all ~56 municipalities/regions
+ LTSAR rail, exceeding the single Mobility-DB style entry.

Per-city realtime (GTFS-RT .pb served by stops.lt / trcapi.dutrys.com) is NOT in
this static index and is intentionally not emitted here.

License: Lithuanian public-sector open data, CC-BY 4.0 (Lithuanian NAP terms).

stdlib only (json, urllib.request, os, re).
"""
import json
import os
import re
import urllib.request

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'feeds_full.json')

CC = 'LT'
LICENSE = 'CC-BY-4.0'
INDEX_URL = 'https://www.visimarsrutai.lt/gtfs/export-report.json'
BASE_URL = 'https://www.visimarsrutai.lt/gtfs/'
NATIONAL_URL = 'https://www.visimarsrutai.lt/gtfs/google_transit.zip'

TIMEOUT = 60
UA = 'Mozilla/5.0 (compatible; gtfs-catalog-scraper/1.0)'

# jobStatus values we treat as a successfully built feed.
OK_STATUS = {'COMPLETED', 'COMPLETE', 'SUCCESS', 'SUCCEEDED', 'OK', 'DONE'}

# City-authority filenames that map to a named city (for the "city" field).
# Keyed by the zip fileName (case-insensitive) -> city display name.
CITY_BY_FILE = {
    'vilniausm.zip': 'Vilnius',
    'kaunom.zip': 'Kaunas',
    'klaipedosm.zip': 'Klaipeda',
    'siauliuM.zip'.lower(): 'Siauliai',
    'panevezioM.zip'.lower(): 'Panevezys',
    'alytausm.zip': 'Alytus',
    'palangosm.zip': 'Palanga',
    'visaginom.zip': 'Visaginas',
    'druskininku.zip': 'Druskininkai',
    'marijampoles.zip': 'Marijampole',
    'birstonosav.zip': 'Birstonas',
    'neringa.zip': 'Neringa',
    'elektrenu.zip': 'Elektrenai',
    'kalvarijos.zip': 'Kalvarija',
    'kazlurudos.zip': 'Kazlu Ruda',
    'rietavo.zip': 'Rietavas',
}


def strip_diacritics(s):
    table = {
        'ą': 'a', 'č': 'c', 'ę': 'e', 'ė': 'e', 'į': 'i', 'š': 's',
        'ų': 'u', 'ū': 'u', 'ž': 'z',
        'Ą': 'A', 'Č': 'C', 'Ę': 'E', 'Ė': 'E', 'Į': 'I', 'Š': 'S',
        'Ų': 'U', 'Ū': 'U', 'Ž': 'Z',
    }
    return ''.join(table.get(ch, ch) for ch in s)


def slugify(s):
    s = strip_diacritics(s).lower()
    s = re.sub(r'[^a-z0-9]+', '-', s)
    return s.strip('-')


def load_existing():
    if not os.path.exists(SRC):
        return []
    try:
        with open(SRC, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (ValueError, OSError):
        return []


def fetch_json(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        raw = resp.read()
    return json.loads(raw.decode('utf-8', errors='replace'))


def main():
    existing = load_existing()
    seen = set()
    for r in existing:
        pu = r.get('producer_url')
        if pu:
            seen.add(pu.rstrip('/'))

    new_records = []

    def add(rec):
        pu = rec.get('producer_url')
        if not pu:
            return
        key = pu.rstrip('/')
        if key in seen:
            return
        seen.add(key)
        new_records.append(rec)

    try:
        index = fetch_json(INDEX_URL)
    except Exception as e:
        print('ERROR fetching index {}: {}'.format(INDEX_URL, e))
        print('+0 new {} feeds'.format(CC))
        return

    authorities = index.get('authorityInfo') or []
    if not isinstance(authorities, list):
        authorities = []

    used_ids = set()

    def unique_id(base):
        cand = base
        n = 2
        while cand in used_ids:
            cand = '{}-{}'.format(base, n)
            n += 1
        used_ids.add(cand)
        return cand

    # (1) Per-authority (municipality / region / rail) feeds
    for entry in authorities:
        if not isinstance(entry, dict):
            continue
        status = str(entry.get('jobStatus', '')).strip().upper()
        if status and status not in OK_STATUS:
            continue  # skip failed / in-progress builds

        file_url = entry.get('fileUrl')
        file_name = entry.get('fileName') or ''
        # Reconstruct URL from fileName if fileUrl missing.
        if not file_url and file_name:
            file_url = BASE_URL + file_name
        if not file_url:
            continue

        agency = (entry.get('agencyName') or '').strip()
        if not agency and file_name:
            agency = os.path.splitext(file_name)[0]
        if not agency:
            agency = 'Unknown authority'

        fn_key = (file_name or os.path.basename(file_url)).lower()
        city = CITY_BY_FILE.get(fn_key)

        # Build a descriptive dataset name with validity window + route count.
        first = entry.get('firstService')
        last = entry.get('lastService')
        routes = entry.get('routesCount')
        parts = ['{} GTFS'.format(agency)]
        meta = []
        if routes not in (None, ''):
            try:
                meta.append('{} routes'.format(int(routes)))
            except (TypeError, ValueError):
                pass
        if first and last:
            meta.append('service {}..{}'.format(first, last))
        if meta:
            name = '{} ({})'.format(parts[0], ', '.join(meta))
        else:
            name = parts[0]

        slug = slugify(agency) or slugify(os.path.splitext(file_name)[0]) or 'authority'
        rec_id = unique_id('{}-{}'.format(CC.lower(), slug))

        add({
            'id': rec_id,
            'provider': agency,
            'name': name,
            'cc': CC,
            'subdiv': None,
            'city': city,
            'producer_url': file_url,
            'hosted_url': None,
            'license': LICENSE,
            'bbox': None,
            'status': 'active',
            'official': True,
        })

    # (2) National aggregate (Google-Transit build). Only if it built OK.
    g = index.get('googleAllInfo')
    g_ok = True
    g_url = NATIONAL_URL
    if isinstance(g, dict):
        gs = str(g.get('jobStatus', '')).strip().upper()
        if gs and gs not in OK_STATUS:
            g_ok = False
        if g.get('fileUrl'):
            g_url = g['fileUrl']
    if g_ok:
        add({
            'id': unique_id('{}-national-aggregate'.format(CC.lower())),
            'provider': 'Visimarsrutai (Lithuanian NAP)',
            'name': 'Lithuania national aggregated GTFS (google_transit.zip)',
            'cc': CC,
            'subdiv': None,
            'city': None,
            'producer_url': g_url,
            'hosted_url': None,
            'license': LICENSE,
            'bbox': None,
            'status': 'active',
            'official': True,
        })

    if new_records:
        out = existing + new_records
        tmp = SRC + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        os.replace(tmp, SRC)

    print('+{} new {} feeds'.format(len(new_records), CC))


if __name__ == '__main__':
    main()
