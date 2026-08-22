#!/usr/bin/env python3
"""Scraper for Luxembourg (LU) GTFS feeds via data.public.lu, the national NAP.

Luxembourg's EU-mandated National Access Point is the data.public.lu open-data
portal (a uData instance), published by the Administration des transports publics
(ATP). There is ONE single nationwide GTFS feed that covers the ENTIRE country
and ALL operators -- CFL rail, Luxtram, AVL (Luxembourg City buses), TICE
(Esch/south buses) and RGTR (national/regional buses). There are NO separate
per-city or per-operator feeds.

The dataset is validity-window versioned: each resource is a zip named
"gtfs-<YYYYMMDD-start>-<YYYYMMDD-end>.zip". The dataset keeps a rolling archive
(hundreds of resources); this scraper picks the resource whose validity window
covers today (falling back to the newest one), so it always emits the CURRENT
feed. Updated weekly, CC-BY-4.0. All public transport in LU is free since 2020.

We enumerate the known LU operators and emit one feed record each, all pointing
at the single current nationwide zip -- so the catalog reflects every operator
even though the aggregator publishes just one file. Dedup is by producer_url, so
when the validity window rolls over and the zip URL changes, a re-run adds the
new operator feeds pointing at the new zip.

uData API shape (verified live):
  GET https://data.public.lu/api/1/datasets/<slug>/
  -> {"title": ..., "license": "cc-by", "resources": [
        {"title": "gtfs-20260819-20261212.zip", "format": "zip",
         "url": "https://download.data.public.lu/resources/.../gtfs-....zip",
         "created_at": ..., "last_modified": ..., "filesize": ...}, ... ]}

stdlib only (json, urllib.request, os, re).
"""
import json
import os
import re
import urllib.request
from datetime import date

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'feeds_full.json')

CC = 'LU'
LICENSE = 'CC-BY-4.0'
SLUG = 'horaires-et-arrets-des-transport-publics-gtfs'
API_URL = 'https://data.public.lu/api/1/datasets/{}/'.format(SLUG)
# Fallback if the API is unreachable: the known-good current bulk zip.
FALLBACK_URL = ('https://download.data.public.lu/resources/'
                'horaires-et-arrets-des-transport-publics-gtfs/'
                '20260821-055311/gtfs-20260819-20261212.zip')

# The nationwide feed's operators. One record each, all -> the single current zip.
# (operator name, city-or-None, note)
OPERATORS = [
    ('AVL (Autobus de la Ville de Luxembourg)', 'Luxembourg City',
     'Luxembourg City municipal buses; part of the single nationwide GTFS feed.'),
    ('Luxtram', 'Luxembourg City',
     'Luxembourg City tram; part of the nationwide GTFS feed.'),
    ('CFL (Societe Nationale des Chemins de Fer Luxembourgeois)', 'Luxembourg City',
     'National rail, hub Luxembourg-Gare; part of the nationwide GTFS feed.'),
    ('TICE (Transport Intercommunal de personnes dans le Canton d\'Esch-sur-Alzette)',
     'Esch-sur-Alzette',
     'Esch/south-region intercommunal buses; part of the nationwide GTFS feed.'),
    ('RGTR (Regime General des Transports Routiers)', None,
     'National/regional bus network reaching all other towns; part of the nationwide GTFS feed.'),
]

DATE_RE = re.compile(r'gtfs-(\d{8})-(\d{8})', re.I)


def slugify(s):
    s = s.lower()
    # keep only the leading acronym / meaningful token: strip parenthetical
    s = re.sub(r'\(.*?\)', '', s)
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


def fetch_json(url, timeout=30):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'gtfs-catalog-scraper/1.0 (+data.public.lu)',
        'Accept': 'application/json',
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))


def pick_current_zip(resources):
    """Return (url, title) for the current-validity GTFS zip, or (None, None)."""
    today = date.today().strftime('%Y%m%d')
    candidates = []  # (start, end, created_at, last_modified, url, title)
    for r in resources:
        if not isinstance(r, dict):
            continue
        fmt = (r.get('format') or '').lower()
        url = r.get('url') or ''
        title = r.get('title') or ''
        if fmt != 'zip' or not url:
            continue
        m = DATE_RE.search(title) or DATE_RE.search(url)
        if not m:
            continue
        start, end = m.group(1), m.group(2)
        created = r.get('created_at') or ''
        modified = r.get('last_modified') or ''
        candidates.append((start, end, created, modified, url, title))

    if not candidates:
        return None, None

    # Prefer a window that covers today.
    covering = [c for c in candidates if c[0] <= today <= c[1]]
    if covering:
        # If several cover today, take the one with the latest start (freshest issue).
        covering.sort(key=lambda c: (c[0], c[2], c[3]), reverse=True)
        return covering[0][4], covering[0][5]

    # Otherwise take the newest by end-date, then created/modified.
    candidates.sort(key=lambda c: (c[1], c[2], c[3], c[0]), reverse=True)
    return candidates[0][4], candidates[0][5]


def resolve_feed():
    """Return (zip_url, feed_title). Falls back to the known bulk URL."""
    try:
        data = fetch_json(API_URL)
    except Exception:
        return FALLBACK_URL, os.path.basename(FALLBACK_URL)

    resources = data.get('resources') or []
    dataset_title = data.get('title') or 'Horaires et arrets des transports publics (GTFS)'
    url, title = pick_current_zip(resources)
    if not url:
        return FALLBACK_URL, os.path.basename(FALLBACK_URL)
    # Feed title: dataset title + validity window for clarity.
    window = title if title else os.path.basename(url)
    return url, '{} — {}'.format(dataset_title, window)


def main():
    existing = load_existing()
    seen = set()
    for r in existing:
        pu = r.get('producer_url')
        if pu:
            seen.add(pu.rstrip('/'))

    new_records = []

    def add(rec):
        key = rec['producer_url'].rstrip('/')
        if key in seen:
            return
        seen.add(key)
        new_records.append(rec)

    zip_url, feed_title = resolve_feed()

    for name, city, note in OPERATORS:
        rec = {
            'id': '{}-{}'.format(CC.lower(), slugify(name)),
            'provider': name,
            'name': '{} ({})'.format(feed_title, note) if note else feed_title,
            'cc': CC,
            'subdiv': None,
            'city': city,
            'producer_url': zip_url,
            'hosted_url': None,
            'license': LICENSE,
            'bbox': None,
            'status': 'active',
            'official': True,
        }
        add(rec)

    if new_records:
        out = existing + new_records
        tmp = SRC + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        os.replace(tmp, SRC)

    print('+{} new {} feeds'.format(len(new_records), CC))


if __name__ == '__main__':
    main()
