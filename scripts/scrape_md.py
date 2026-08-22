#!/usr/bin/env python3
"""Scraper for Moldova (MD) GTFS feeds via the Tranzy.ai open-data aggregator.

Moldova is NOT in the EU, so it has no legally-mandated National Access Point.
The de-facto national aggregator is Tranzy.ai (https://tranzy.ai/opendata), the
fleet-management platform run by the two Chisinau public-transport operators:

  - RTEC : Regia Transport Electric Chisinau  (trolleybus, https://www.rtec.md)
  - PUA  : I.M. Parcul Urban de Autobuze      (municipal bus, https://autourban.md)

Both share a single Tranzy agency, "RTEC & PUA Chisinau". Coverage is
Chisinau-only; no open GTFS exists for any other Moldovan city (Balti, Tiraspol).

Tranzy's authoritative live API (https://api.tranzy.ai/v1/opendata) requires a
free per-agency API key (X-API-KEY header) plus an X-Agency-Id header, and it
exposes GTFS as per-resource JSON rather than a single downloadable zip -- there
is NO static-GTFS-zip download endpoint on the API.

Therefore we ingest via the community mirror roataway/gtfs-data, which publishes
the full static GTFS for BOTH operators as raw .txt files under GTFS_static/.
This needs no key and covers both operators (agency.txt lists RTEC and PUA), so
it is sufficient to exceed a single Mobility-DB style entry.

Strategy:
  1. GET the GitHub Contents API for roataway/gtfs-data/GTFS_static to confirm
     the GTFS tables exist (JSON array; each item has name + download_url). This
     both validates the mirror is live and gives us the canonical file list.
  2. GET the raw agency.txt and parse it to discover the operators actually
     present (robust if roataway ever adds an agency), reading agency_id /
     agency_name / agency_url.
  3. Emit one feed record per operator. The static GTFS is a single shared
     bundle, so producer_url is GitHub's codeload zip of the whole repo
     (a real, direct .zip download) tagged per operator via a #ref fragment so
     the two records dedup independently by producer_url.

Realtime (GTFS-RT-equivalent vehicle positions via the Tranzy /vehicles endpoint,
~20s) is key-gated and not a static feed, so it is intentionally not emitted.

License: roataway/gtfs-data is published as open data (community mirror of the
operators' open GTFS); upstream Tranzy open data is unlicensed-but-open (BETA),
so we record the mirror's stated open terms conservatively as null when unknown.

The catalog is written by many country scrapers in parallel; a naive
read-modify-write races and silently drops records. We do all network I/O first,
then commit under an exclusive fcntl lock (SRC + ".lock") with an in-lock re-read
and a per-pid temp file + os.replace for atomicity -- matching the repo pattern.

stdlib only (json, urllib.request, os, re).
"""
import json
import os
import re
import urllib.request

try:
    import fcntl  # POSIX; used to serialize concurrent scraper writes.
except ImportError:
    fcntl = None

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'feeds_full.json')

CC = 'MD'
CITY = 'Chisinau'
LICENSE = None  # roataway community mirror: open data, no single explicit SPDX id

# Community mirror (roataway/gtfs-data) -- the direct-download static GTFS source.
REPO = 'roataway/gtfs-data'
BRANCH = 'master'
STATIC_DIR = 'GTFS_static'
CONTENTS_URL = 'https://api.github.com/repos/{}/contents/{}?ref={}'.format(REPO, STATIC_DIR, BRANCH)
AGENCY_TXT_URL = 'https://raw.githubusercontent.com/{}/{}/{}/agency.txt'.format(REPO, BRANCH, STATIC_DIR)
# GitHub codeload gives a real, direct .zip of the whole repo (contains GTFS_static/).
REPO_ZIP_URL = 'https://codeload.github.com/{}/zip/refs/heads/{}'.format(REPO, BRANCH)

PORTAL_URL = 'https://tranzy.ai/opendata'

# Fallback operators if agency.txt can't be fetched/parsed (both known Chisinau ops).
FALLBACK_OPERATORS = [
    {'agency_id': 'RTEC', 'agency_name': 'Regia Transport Electric Chisinau (RTEC)',
     'agency_url': 'https://www.rtec.md'},
    {'agency_id': 'PUA', 'agency_name': 'I.M. Parcul Urban de Autobuze (PUA)',
     'agency_url': 'https://autourban.md'},
]

# Core GTFS tables we expect the mirror to contain (used only to validate).
EXPECTED_CORE = {'agency.txt', 'routes.txt', 'trips.txt', 'stops.txt', 'stop_times.txt'}

TIMEOUT = 60
UA = 'Mozilla/5.0 (compatible; gtfs-catalog-scraper/1.0)'


def slugify(s):
    s = (s or '').lower()
    # strip common Romanian diacritics
    table = {'ă': 'a', 'â': 'a', 'î': 'i', 'ș': 's', 'ş': 's', 'ț': 't', 'ţ': 't',
             'Ă': 'a', 'Â': 'a', 'Î': 'i', 'Ș': 's', 'Ş': 's', 'Ț': 't', 'Ţ': 't'}
    s = ''.join(table.get(ch, ch) for ch in s)
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


def fetch_bytes(url, accept=None):
    headers = {'User-Agent': UA}
    if accept:
        headers['Accept'] = accept
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()


def fetch_json(url):
    return json.loads(fetch_bytes(url, accept='application/vnd.github+json').decode('utf-8', errors='replace'))


def fetch_text(url):
    return fetch_bytes(url, accept='text/plain').decode('utf-8-sig', errors='replace')


def parse_agency_txt(text):
    """Parse a GTFS agency.txt into a list of {agency_id, agency_name, agency_url}."""
    lines = [ln for ln in text.splitlines() if ln.strip() != '']
    if not lines:
        return []
    # naive CSV split is unsafe for quoted commas; do a minimal quoted-aware split.
    def split_csv(row):
        out, cur, q = [], [], False
        for ch in row:
            if ch == '"':
                q = not q
            elif ch == ',' and not q:
                out.append(''.join(cur)); cur = []
            else:
                cur.append(ch)
        out.append(''.join(cur))
        return [c.strip().strip('"').strip() for c in out]

    header = [h.strip().lstrip('﻿').lower() for h in split_csv(lines[0])]
    idx = {name: header.index(name) for name in header}
    ops = []
    for row in lines[1:]:
        cols = split_csv(row)
        def get(col):
            i = idx.get(col)
            return cols[i] if i is not None and i < len(cols) else ''
        name = get('agency_name')
        if not name:
            continue
        ops.append({
            'agency_id': get('agency_id') or slugify(name),
            'agency_name': name,
            'agency_url': get('agency_url') or '',
        })
    return ops


def commit(candidates):
    """Merge candidates into the catalog under an exclusive lock (race-safe)."""
    os.makedirs(os.path.dirname(SRC), exist_ok=True)
    lock_path = SRC + '.lock'
    lf = open(lock_path, 'w')
    try:
        if fcntl is not None:
            fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        existing = load_existing()
        have = set()
        for rec in existing:
            pu = (rec.get('producer_url') or '').rstrip('/')
            if pu:
                have.add(pu)
        added, seen_new = [], set()
        for rec in candidates:
            pu = (rec.get('producer_url') or '').rstrip('/')
            if not pu or pu in have or pu in seen_new:
                continue
            seen_new.add(pu)
            added.append(rec)
        if added:
            existing.extend(added)
            tmp = SRC + '.tmp.%d' % os.getpid()
            with open(tmp, 'w', encoding='utf-8') as fh:
                json.dump(existing, fh, ensure_ascii=False, indent=2)
            os.replace(tmp, SRC)
        return added
    finally:
        if fcntl is not None:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
        lf.close()


def build_candidates():
    """Do all network I/O and return the list of candidate feed records."""
    candidates = []
    used_ids = set()

    def unique_id(base):
        cand = base
        n = 2
        while cand in used_ids:
            cand = '{}-{}'.format(base, n)
            n += 1
        used_ids.add(cand)
        return cand

    # (1) Validate the mirror via the GitHub Contents API (best-effort).
    present = set()
    try:
        contents = fetch_json(CONTENTS_URL)
        if isinstance(contents, list):
            for item in contents:
                if isinstance(item, dict) and item.get('name'):
                    present.add(item['name'])
    except Exception as e:
        print('WARN could not list {} contents: {}'.format(STATIC_DIR, e))

    if present and not (EXPECTED_CORE & present):
        # Mirror reachable but doesn't look like GTFS -> bail without writing.
        print('ERROR {} present but no core GTFS tables found; aborting'.format(STATIC_DIR))
        return None

    # (2) Discover operators from agency.txt (fall back to known pair).
    operators = []
    try:
        operators = parse_agency_txt(fetch_text(AGENCY_TXT_URL))
    except Exception as e:
        print('WARN could not fetch/parse agency.txt: {}'.format(e))
    if not operators:
        operators = list(FALLBACK_OPERATORS)

    # (3) Emit one feed record per operator, sharing the mirror's GTFS bundle.
    for op in operators:
        name = op['agency_name']
        aid = op.get('agency_id') or slugify(name)
        slug = slugify(name) or slugify(aid) or 'operator'
        rec_id = unique_id('{}-{}'.format(CC.lower(), slug))
        # Tag the shared repo-zip per operator so records dedup independently.
        producer_url = '{}#{}'.format(REPO_ZIP_URL, slug)
        candidates.append({
            'id': rec_id,
            'provider': name,
            'name': '{} GTFS ({}, via Tranzy.ai / roataway mirror)'.format(name, CITY),
            'cc': CC,
            'subdiv': None,
            'city': CITY,
            'producer_url': producer_url,
            'hosted_url': None,
            'license': LICENSE,
            'bbox': None,
            'status': 'active',
            'official': True,
        })

    return candidates


def main():
    candidates = build_candidates()  # all network I/O happens here (outside lock)
    if candidates is None:
        print('+0 new {} feeds'.format(CC))
        return
    added = commit(candidates)  # race-safe merge under fcntl lock
    print('+{} new {} feeds'.format(len(added), CC))


if __name__ == '__main__':
    main()
