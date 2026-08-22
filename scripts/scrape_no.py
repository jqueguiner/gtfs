#!/usr/bin/env python3
"""Scraper for Norway (NO) GTFS feeds via Entur, the national NAP aggregator.

Entur AS is Norway's legally-mandated National Access Point. It runs the national
timetable registry, aggregating ~60 operators/authorities under the NLOD open
license. Native format is the Nordic NeTEx Profile; GTFS is auto-derived nightly.

Two output flavors live in the same public GCS bucket 'marduk-production':
  (1) national aggregated GTFS  -> covers ALL of Norway (one big zip)
  (2) per-codespace GTFS zips   -> one per operator/authority

  national : outbound/gtfs/rb_norway-aggregated-gtfs.zip     (== Mobility DB mdb-1078)
  per-op   : outbound/gtfs/rb_<codespace-lowercase>-aggregated-gtfs.zip

There is NO JSON dataset-list endpoint; the codespace list (List of current
Codespaces on the Entur Confluence) is the effective index. Codespaces are
3-letter provider codes. This scraper enumerates the timetable-data providers and
emits one per-operator feed each, PLUS the national aggregate -> exceeding the
single-feed Mobility Database entry.

GOTCHA: the GCS bucket returns HTTP 403 on HEAD and on Range (bytes=) requests,
and also for geo-restricted client IPs ("service not available in your location").
So we do NOT probe URLs for existence here -- the codespace list is authoritative
and the objects are publicly downloadable via a full GET (as mdb-1078 relies on).
Records are emitted unconditionally from the known codespace catalog.

Rate limit: Entur asks for max ~1 download per file per 24h -- this scraper only
BUILDS the catalog of URLs, it does not download the zips, so it is rate-safe.

stdlib only.
"""
import json
import os
import re

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'feeds_full.json')

CC = 'NO'
LICENSE = 'NLOD'  # Norwegian License for Open Government Data
GTFS_TMPL = 'https://storage.googleapis.com/marduk-production/outbound/gtfs/rb_{cs}-aggregated-gtfs.zip'
NATIONAL_URL = 'https://storage.googleapis.com/marduk-production/outbound/gtfs/rb_norway-aggregated-gtfs.zip'

# Timetable-data providers from Entur's "List of current Codespaces".
# (codespace, operator/authority name, subdiv/county-or-None, city-or-None)
# We intentionally exclude mobility (bike/scooter Y* codes), utility-data,
# and non-Norwegian (Swedish) codespaces -- those are not Norway GTFS transit feeds.
CODESPACES = [
    ('AKT', 'Agder kollektivtrafikk', 'Agder', 'Kristiansand'),
    ('ATB', 'AtB', 'Trøndelag', 'Trondheim'),
    ('ASH', 'Arctic Sea Hotel & Apartments', None, None),
    ('AVI', 'Avinor', None, None),
    ('BNR', 'Bane NOR', None, None),
    ('BEF', 'Beffen', 'Vestland', 'Bergen'),
    ('BOR', 'Boreal', None, None),
    ('BSR', 'Bussring', None, None),
    ('BRA', 'Brakar', 'Buskerud', 'Drammen'),
    ('NYC', 'Bygdøyfergen', 'Oslo', 'Oslo'),
    ('COL', 'Color Line', None, None),
    ('TEL', 'Farte', 'Telemark', 'Skien'),
    ('FJT', 'Fjord Tours', None, None),
    ('FLI', 'Flixbus', None, None),
    ('FLT', 'Flytoget', None, 'Oslo'),
    ('FTR', 'Flåm Travel', 'Vestland', 'Flåm'),
    ('FLB', 'Flåmsbana', 'Vestland', 'Flåm'),
    ('OSC', 'Forsvarsbygg (Oscarsborgfergen)', None, None),
    ('MOR', 'Fram', 'Møre og Romsdal', None),
    ('GFS', 'Geiranger Fjordservice', 'Møre og Romsdal', 'Geiranger'),
    ('GOA', 'Go-Ahead Nordic', None, None),
    ('GOF', 'Go Fjords', None, None),
    ('HAV', 'Havila', None, None),
    ('HUR', 'Hurtigruten', None, None),
    ('HOG', 'Høgsfjordferja', 'Rogaland', None),
    ('INN', 'Innlandet fylkeskommune', 'Innlandet', 'Hamar'),
    ('KOL', 'Kolumbus', 'Rogaland', 'Stavanger'),
    ('SOF', 'Kringom', 'Vestland', None),
    ('OIS', 'MF Øisang', None, None),
    ('NWY', 'NOR-WAY Bussekspress', None, None),
    ('NOR', 'Nordland fylkeskommune', 'Nordland', 'Bodø'),
    ('NBU', 'Connect Bus Flybuss', None, None),
    ('VIP', 'Oslo VIP Transporttjenester', 'Oslo', 'Oslo'),
    ('RUT', 'Ruter', 'Oslo og Akershus', 'Oslo'),
    ('SJV', 'SJ', None, None),
    ('SJN', 'SJ NORD', None, None),
    ('SKY', 'Skyss', 'Vestland', 'Bergen'),
    ('FIN', 'Snelandia', 'Finnmark', None),
    ('STB', 'Stadbussen', None, None),
    ('TID', 'Tide', None, None),
    ('TRO', 'Troms fylkestrafikk', 'Troms', 'Tromsø'),
    ('TTS', 'Torghatten', None, None),
    ('ULR', 'Ulriken', 'Vestland', 'Bergen'),
    ('UNI', 'Unibuss', None, None),
    ('VOT', 'Vestfold og Telemark', 'Vestfold og Telemark', 'Tønsberg'),
    ('VKT', 'VKT', 'Vestfold', 'Tønsberg'),
    ('NSB', 'Vy (formerly NSB)', None, None),
    ('GJB', 'Vy Gjøvikbanen', None, None),
    ('VYG', 'Vy-group', None, None),
    ('VYB', 'Vy Buss AB', None, None),
    ('VYX', 'Vy Buss AS', None, None),
    ('OST', 'Østfold kollektivtrafikk', 'Østfold', None),
    ('ATU', 'Ålesund Turvogn Service', 'Møre og Romsdal', 'Ålesund'),
]


def slugify(s):
    s = s.lower()
    s = s.replace('ø', 'o').replace('æ', 'ae').replace('å', 'a')
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

    # (1) National aggregate -- covers all of Norway (mirrors Mobility DB mdb-1078)
    add({
        'id': '{}-{}'.format(CC.lower(), 'entur-national'),
        'provider': 'Entur',
        'name': 'Norway aggregated GTFS (national)',
        'cc': CC,
        'subdiv': None,
        'city': None,
        'producer_url': NATIONAL_URL,
        'hosted_url': None,
        'license': LICENSE,
        'bbox': None,
        'status': 'active',
        'official': True,
    })

    # (2) Per-codespace operator feeds
    for cs, name, subdiv, city in CODESPACES:
        url = GTFS_TMPL.format(cs=cs.lower())
        add({
            'id': '{}-{}'.format(CC.lower(), slugify(name)),
            'provider': name,
            'name': '{} GTFS (Entur codespace {})'.format(name, cs),
            'cc': CC,
            'subdiv': subdiv,
            'city': city,
            'producer_url': url,
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
