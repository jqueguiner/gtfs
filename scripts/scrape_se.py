#!/usr/bin/env python3
"""
Scraper: Sweden (SE) — Trafiklab / Samtrafiken i Sverige AB (Swedish National Access Point).

Trafiklab is Sweden's official NAP, operated by Samtrafiken. It exposes THREE static
GTFS products, all CC0 1.0, all behind a free API key from https://developer.trafiklab.se
and all requiring client-side GZIP:

  (1) GTFS Sverige 2  — single aggregated national zip covering ALL Swedish PT.
        https://api.resrobot.se/gtfs/sweden.zip?key={apikey}
  (2) GTFS Sweden 3   — newer aggregated national zip (now includes all Trafikverket rail).
        https://opendata.samtrafiken.se/gtfs-sweden/sweden.zip?key={apikey}
  (3) GTFS Regional   — per-operator zips, one per Swedish region (higher detail + RT).
        https://opendata.samtrafiken.se/gtfs/{operator}/{operator}.zip?key={apikey}

There is NO JSON feed-list endpoint. The authoritative operator list is the static
{operator} enum in the OpenAPI spec:
  https://github.com/trafiklab/openApi-docs/blob/master/gtfsRegionalStatic.yaml
Endpoints are direct binary .zip downloads (HTTP 406 on missing gzip / 403 on bad key,
never 404), so we cannot enumerate via a listing — we materialize the fixed enum below
(verified against the spec) and best-effort probe each with a conditional HEAD.

stdlib only. Appends records to data/feeds_full.json (a JSON array), dedup by producer_url.
"""

import json
import os
import re
import urllib.request
import urllib.error

SRC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "feeds_full.json",
)

CC = "SE"
LICENSE = "CC0-1.0"
KEY = "{apikey}"  # placeholder — free key from https://developer.trafiklab.se
TIMEOUT = 25
# Server rejects requests without gzip acceptance (HTTP 406), so always advertise it.
HEADERS = {
    "Accept-Encoding": "gzip",
    "User-Agent": "adresses-gtfs-catalog/1.0 (+https://github.com/jqueguiner/gtfs)",
}

# National aggregated feeds (whole-country).
NATIONAL = [
    {
        "slug": "gtfs-sverige-2",
        "provider": "Samtrafiken i Sverige AB",
        "name": "GTFS Sverige 2 (national aggregated, all Swedish public transport)",
        "url": "https://api.resrobot.se/gtfs/sweden.zip?key=" + KEY,
    },
    {
        "slug": "gtfs-sweden-3",
        "provider": "Samtrafiken i Sverige AB",
        "name": "GTFS Sweden 3 (national aggregated, incl. all Trafikverket rail)",
        "url": "https://opendata.samtrafiken.se/gtfs-sweden/sweden.zip?key=" + KEY,
    },
]

# Authoritative operator enum from gtfsRegionalStatic.yaml — one feed per Swedish region.
# Each: operator code -> (provider name, subdiv/region, representative city).
OPERATORS = {
    "blekinge":     ("Blekingetrafiken",                     "Blekinge",                 "Karlskrona"),
    "dintur":       ("Din Tur (Kollektivtrafikmyndigheten Vasternorrland)", "Vasternorrland", "Sundsvall"),
    "dt":           ("Dalatrafik",                            "Dalarna",                  "Falun"),
    "gotland":      ("Gotlands Kollektivtrafik",              "Gotland",                  "Visby"),
    "halland":      ("Hallandstrafiken",                      "Halland",                  "Halmstad"),
    "jamtland":     ("Lanstrafiken i Jamtland",               "Jamtland",                 "Ostersund"),
    "jlt":          ("Jonkopings Lanstrafik",                 "Jonkopings lan",           "Jonkoping"),
    "klt":          ("Kalmar Lanstrafik",                     "Kalmar lan",               "Kalmar"),
    "krono":        ("Lanstrafiken Kronoberg",                "Kronoberg",                "Vaxjo"),
    "norrbotten":   ("Lanstrafiken i Norrbotten",             "Norrbotten",               "Lulea"),
    "orebro":       ("Lanstrafiken Orebro",                   "Orebro lan",               "Orebro"),
    "otraf":        ("Ostgotatrafiken",                       "Ostergotland",             "Linkoping"),
    "sj":           ("SJ AB",                                 None,                       None),
    "skane":        ("Skanetrafiken",                         "Skane",                    "Malmo"),
    "sl":           ("Storstockholms Lokaltrafik (SL)",       "Stockholms lan",           "Stockholm"),
    "sormland":     ("Sormlandstrafiken",                     "Sodermanland",             "Nykoping"),
    "ul":           ("Upplands Lokaltrafik (UL)",             "Uppsala lan",              "Uppsala"),
    "varm":         ("Varmlandstrafik",                       "Varmland",                 "Karlstad"),
    "vasterbotten": ("Lanstrafiken i Vasterbotten",           "Vasterbotten",             "Umea"),
    "vastmanland":  ("Vastmanlands Lokaltrafik (VL)",         "Vastmanland",              "Vasteras"),
    "vt":           ("Vasttrafik",                            "Vastra Gotaland",          "Goteborg"),
    "xt":           ("X-Trafik",                              "Gavleborg",                "Gavle"),
}


def slugify(s):
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def load_existing():
    try:
        with open(SRC, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except (FileNotFoundError, ValueError):
        pass
    return []


def probe(url):
    """Best-effort reachability check. Never raises; return True unless we get a
    definitive 404 (feed genuinely gone). Key is a placeholder so 401/403/406 are
    expected and must NOT drop the record."""
    real = url.replace("{apikey}", "")  # probe base path without a key
    req = urllib.request.Request(real, method="HEAD", headers=HEADERS)
    try:
        urllib.request.urlopen(req, timeout=TIMEOUT)
        return True
    except urllib.error.HTTPError as e:
        # 404 = gone. Anything else (401/403/406/etc) = endpoint exists, auth/gzip gated.
        return e.code != 404
    except Exception:
        # timeout / DNS / TLS — don't punish the record; enum is authoritative.
        return True


def make_record(rec_id, provider, name, subdiv, city, producer_url):
    return {
        "id": rec_id,
        "provider": provider,
        "name": name,
        "cc": CC,
        "subdiv": subdiv,
        "city": city,
        "producer_url": producer_url,
        "hosted_url": None,
        "license": LICENSE,
        "bbox": None,
        "status": "active",
        "official": True,
    }


def main():
    existing = load_existing()
    seen = {r.get("producer_url", "").rstrip("/") for r in existing if isinstance(r, dict)}

    candidates = []

    # (1)+(2) National aggregated feeds.
    for feed in NATIONAL:
        candidates.append(
            make_record(
                CC.lower() + "-" + feed["slug"],
                feed["provider"],
                feed["name"],
                None,
                None,
                feed["url"],
            )
        )

    # (3) Per-operator regional feeds (authoritative enum).
    for code, (provider, subdiv, city) in OPERATORS.items():
        url = "https://opendata.samtrafiken.se/gtfs/{op}/{op}.zip?key={k}".format(op=code, k=KEY)
        name = "GTFS Regional — {p} ({op})".format(p=provider, op=code)
        candidates.append(
            make_record(
                CC.lower() + "-" + slugify(code),
                provider,
                name,
                subdiv,
                city,
                url,
            )
        )

    added = 0
    for rec in candidates:
        key = rec["producer_url"].rstrip("/")
        if key in seen:
            continue
        if not probe(rec["producer_url"]):
            continue
        existing.append(rec)
        seen.add(key)
        added += 1

    with open(SRC, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    print("+{n} new {cc} feeds".format(n=added, cc=CC))


if __name__ == "__main__":
    main()
