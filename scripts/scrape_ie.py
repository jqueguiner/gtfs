#!/usr/bin/env python3
"""Scraper for Ireland (IE) — Transport for Ireland (TFI) / National Transport
Authority (NTA), Ireland's de-facto National Access Point.

Pulls the machine-readable operator index CSV
  https://www.transportforireland.ie/transitData/Data/GTFS Operator Files.csv
which maps each operator to its GTFS zip filename(s) (a per-operator zip plus the
bundle zips GTFS_All / GTFS_not_dublin / GTFS_Small_Operators / GTFS_Realtime /
GTFS_NI). For every operator we emit one catalog record pointing at the best
available direct GTFS zip: a dedicated per-operator zip when one exists, else the
most specific bundle available (the national bulk GTFS_All.zip contains every
operator and is the last-resort fallback).

Data licensed CC BY 4.0 (attributed to the National Transport Authority).
stdlib only: json, urllib.request, os, re.
"""
import json
import os
import re
import urllib.request

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   'data', 'feeds_full.json')

BASE = "https://www.transportforireland.ie/transitData/Data/"
CSV_URL = BASE + "GTFS%20Operator%20Files.csv"
BULK_URL = BASE + "GTFS_All.zip"
LICENSE = "CC-BY-4.0"
CC = "IE"

# Bundle / aggregate zips that are NOT a single-operator feed. Many operators
# have no dedicated per-operator zip and are only published inside a bundle; for
# those we point at the most specific bundle available (see BUNDLE_PREF), which
# is a legitimate direct GTFS zip URL. GTFS_All.zip (every operator nationwide)
# is the last-resort fallback.
BUNDLE_ZIPS = {
    "GTFS_All.zip",
    "GTFS_not_dublin.zip",
    "GTFS_Small_Operators.zip",
    "GTFS_Realtime.zip",
    "GTFS_NI.zip",
}

# When only bundle zips are available for an operator, prefer the most specific
# one (lower index = more specific). GTFS_Realtime is not a static-schedule feed
# so it is never chosen as the producer_url.
BUNDLE_PREF = [
    "GTFS_NI.zip",
    "GTFS_Small_Operators.zip",
    "GTFS_not_dublin.zip",
    "GTFS_All.zip",
]

# Northern Ireland (Translink) operators are published in the same NAP but are
# UK/GB jurisdiction; we tag their subdiv. They only ship inside GTFS_NI.zip.
NI_OPERATORS = {
    "enterprise", "foyle metro", "glider", "goldline express", "metro",
    "nirailways", "ulsterbus", "ulsterbus town services",
}

# Best-effort city hints for the well-known city operators (sample-derived).
CITY_HINTS = [
    (re.compile(r"dublin bus|nitelink|swords express|dublin express|dublin coach",
                re.I), "Dublin"),
    (re.compile(r"go-?ahead", re.I), "Dublin"),
    (re.compile(r"\bluas\b", re.I), "Dublin"),
    (re.compile(r"city direct", re.I), "Galway"),
    (re.compile(r"cork cobh|west cork", re.I), "Cork"),
]

UA = {"User-Agent": "gtfs-catalog-scraper/1.0 (+https://github.com/jqueguiner/gtfs)"}


def fetch(url, timeout=60):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8-sig", "replace")


def parse_csv(text):
    """Minimal RFC4180-ish parser (stdlib-only, no csv module).
    Handles double-quoted fields with embedded commas and CRLF/LF newlines."""
    rows = []
    field = []
    row = []
    in_q = False
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if in_q:
            if c == '"':
                if i + 1 < n and text[i + 1] == '"':
                    field.append('"')
                    i += 2
                    continue
                in_q = False
                i += 1
                continue
            field.append(c)
            i += 1
            continue
        if c == '"':
            in_q = True
            i += 1
            continue
        if c == ',':
            row.append("".join(field))
            field = []
            i += 1
            continue
        if c in "\r\n":
            if c == '\r' and i + 1 < n and text[i + 1] == '\n':
                i += 1
            row.append("".join(field))
            field = []
            if any(v.strip() for v in row):
                rows.append(row)
            row = []
            i += 1
            continue
        field.append(c)
        i += 1
    if field or row:
        row.append("".join(field))
        if any(v.strip() for v in row):
            rows.append(row)
    return rows


def slugify(s):
    s = s.lower()
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "op"


def city_for(name):
    for rx, city in CITY_HINTS:
        if rx.search(name):
            return city
    return None


# TFI Local Link rural/regional variants encode their area in the name, e.g.
# "TFI Local Link Cork" or "TFI Local Link Limerick Clare"; capture that as the
# subdiv so the ~15 regional feeds are distinguishable in the catalog.
_LOCAL_LINK = re.compile(r"^TFI Local Link\s+(.+)$", re.I)


def subdiv_for(name, ni_default):
    if ni_default:
        return "Northern Ireland"
    m = _LOCAL_LINK.match(name)
    if m:
        return m.group(1).strip()
    return None


def main():
    try:
        text = fetch(CSV_URL)
    except Exception as e:
        print("failed to fetch operator index CSV:", e)
        return
    rows = parse_csv(text)
    if not rows:
        print("empty CSV")
        return
    # Drop header if present.
    if rows and rows[0] and rows[0][0].strip().lower() == "operator":
        rows = rows[1:]

    # Group links per operator name (preserve first-seen order).
    by_op = {}
    order = []
    for r in rows:
        if len(r) < 2:
            continue
        name = r[0].strip()
        link = r[1].strip()
        if not name or not link.lower().endswith(".zip"):
            continue
        if name not in by_op:
            by_op[name] = []
            order.append(name)
        by_op[name].append(link)

    # Load existing catalog (tolerant) + snapshot of pre-run producer_urls.
    try:
        with open(SRC, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            data = []
    except Exception:
        data = []
    preexisting = set()
    for rec in data:
        pu = rec.get("producer_url")
        if pu:
            preexisting.add(pu.rstrip("/"))

    added = 0
    ids = set()
    for name in order:
        links = by_op[name]
        # Prefer a dedicated per-operator zip. If none exists, use the most
        # specific bundle zip available for this operator (NI > Small_Operators
        # > not_dublin > All). Bundle URLs are legitimately shared across the
        # operators they contain, so we do NOT skip an operator merely because a
        # previously-processed operator used the same bundle -- we only dedup
        # against records that already existed in the catalog before this run.
        per_op = None
        for lk in links:
            fn = lk.rsplit("/", 1)[-1]
            if fn not in BUNDLE_ZIPS:
                per_op = lk
                break
        if per_op:
            producer_url = per_op
        else:
            producer_url = BULK_URL
            avail = {lk.rsplit("/", 1)[-1]: lk for lk in links}
            for fn in BUNDLE_PREF:
                if fn in avail:
                    producer_url = avail[fn]
                    break
        key = producer_url.rstrip("/")
        # Dedup only against the catalog as it stood at the start of this run.
        if key in preexisting:
            continue

        low = name.lower()
        subdiv = subdiv_for(name, low in NI_OPERATORS)

        base_slug = slugify(name)
        slug = base_slug
        n2 = 2
        while f"{CC.lower()}-{slug}" in ids:
            slug = f"{base_slug}-{n2}"
            n2 += 1
        ids.add(f"{CC.lower()}-{slug}")

        rec = {
            "id": f"{CC.lower()}-{slug}",
            "provider": name,
            "name": f"{name} GTFS (TFI/NTA)",
            "cc": CC,
            "subdiv": subdiv,
            "city": city_for(name),
            "producer_url": producer_url,
            "hosted_url": None,
            "license": LICENSE,
            "bbox": None,
            "status": "active",
            "official": True,
        }
        data.append(rec)
        added += 1

    tmp = SRC + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, SRC)
    print(f"+{added} new {CC} feeds")


if __name__ == "__main__":
    main()
