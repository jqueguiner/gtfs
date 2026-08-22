#!/usr/bin/env python3
r"""
Scraper: Poland (PL) — Otwarte Dane Transportowe (ODT) / zbiorkom.live GTFS CDN.

THE practical enumerator for Poland's open transit. cdn.zbiorkom.live/gtfs/ is an
open Nginx *autoindex* directory listing ~64 GTFS static .zip feeds — every major
metro (Warsaw, Krakow, Wroclaw, Lodz, Poznan, Tricity, GZM/Katowice, Szczecin, ...),
their suburban operators, and the full national rail (PKP) set — refreshed daily.

odt.org.pl/en is only the human-facing Next.js catalog front-end backed by this CDN.
Poland's LEGAL National Access Point is dane.gov.pl dataset 1739 (Krajowy Punkt
Dostepowy / KPD), but that is merely a CSV/XLSX *registry* of which operators provide
multimodal data — it does NOT host GTFS zips centrally. So we scrape the zbiorkom CDN.

Approach: GET https://cdn.zbiorkom.live/gtfs/ with a browser User-Agent (the default
urllib UA gets a 403). The response is plain Nginx autoindex HTML; parse anchors
matching href="([^"]+\.zip)". Each is a GTFS static feed at
  https://cdn.zbiorkom.live/gtfs/{filename}
We map each slug to city / operator / region via SLUGMAP; unknown slugs (the CDN adds
feeds over time) still get emitted with a best-effort derived provider/city so the
catalog stays complete.

stdlib only (json, os, re, urllib). Appends to data/feeds_full.json (a JSON array),
dedup by producer_url.rstrip('/'). Prints '+N new PL feeds'.
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

CC = "PL"
# ODT / zbiorkom aggregate open GTFS; no single blanket license is asserted on the
# CDN itself (per-operator terms vary). Leave null rather than assert a wrong one.
LICENSE = None
BASE = "https://cdn.zbiorkom.live/gtfs/"
TIMEOUT = 30
HEADERS = {
    # The CDN 403s the default urllib User-Agent; a browser UA is required.
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
}

# slug (filename without .zip) -> (provider, name, subdiv/voivodeship, city)
# subdiv = voivodeship (wojewodztwo). None city => operator/rail-wide feed.
SLUGMAP = {
    # --- Bialystok (Podlaskie) ---
    "bialystok":          ("BKM / ZDiZ Bialystok",              "GTFS — Bialystok municipal transit (BKM)",              "Podlaskie",            "Bialystok"),
    "bialystok-nova":     ("KP Nova (Bialystok agglomeration)", "GTFS — Bialystok suburban: KP Nova",                    "Podlaskie",            "Bialystok"),
    "bialystok-turosn":   ("Gmina Turosn Koscielna",            "GTFS — Bialystok suburban: Turosn Koscielna",           "Podlaskie",            "Turosn Koscielna"),
    "bialystok-wschod":   ("Bialystok Wschod (eastern communes)", "GTFS — Bialystok suburban: Wschod",                   "Podlaskie",            "Bialystok"),
    # --- Czestochowa (Slaskie) ---
    "czestochowa":        ("MPK Czestochowa",                   "GTFS — Czestochowa (MPK, tram + bus)",                  "Slaskie",              "Czestochowa"),
    # --- Elblag (Warminsko-Mazurskie) ---
    "elblag":             ("ZKM Elblag",                        "GTFS — Elblag (ZKM, tram + bus)",                       "Warminsko-Mazurskie",  "Elblag"),
    # --- Elk (Warminsko-Mazurskie) ---
    "elk":                ("MZK Elk",                           "GTFS — Elk (MZK)",                                      "Warminsko-Mazurskie",  "Elk"),
    # --- Gorzow Wielkopolski (Lubuskie) ---
    "gorzow":             ("MZK Gorzow Wielkopolski",           "GTFS — Gorzow Wielkopolski (MZK, tram + bus)",          "Lubuskie",             "Gorzow Wielkopolski"),
    # --- GZM / Silesian conurbation (Slaskie) ---
    "gzm":                ("ZTM GZM (Gornoslasko-Zaglebiowska Metropolia)", "GTFS — GZM metropolis-wide (Katowice, Gliwice, Sosnowiec, Bytom, Zabrze, tram + bus)", "Slaskie", "Katowice"),
    # --- Kielce (Swietokrzyskie) ---
    "kielce":             ("ZTM Kielce",                        "GTFS — Kielce (ZTM)",                                   "Swietokrzyskie",       "Kielce"),
    # --- Krakow (Malopolskie) ---
    "krakow-bus":         ("MPK Krakow",                        "GTFS — Krakow buses (MPK)",                             "Malopolskie",          "Krakow"),
    "krakow-tram":        ("MPK Krakow",                        "GTFS — Krakow trams (MPK)",                             "Malopolskie",          "Krakow"),
    "krakow-mobilis":     ("Mobilis (Krakow agglomeration)",    "GTFS — Krakow private operator: Mobilis",               "Malopolskie",          "Krakow"),
    # --- Kutno (Lodzkie) ---
    "kutno":              ("MZK Kutno",                         "GTFS — Kutno (MZK)",                                    "Lodzkie",              "Kutno"),
    # --- Legnica (Dolnoslaskie) ---
    "legnica":            ("MPK Legnica",                       "GTFS — Legnica (MPK)",                                  "Dolnoslaskie",         "Legnica"),
    # --- Leszno (Wielkopolskie) ---
    "leszno":             ("MZK Leszno",                        "GTFS — Leszno (MZK)",                                   "Wielkopolskie",        "Leszno"),
    # --- Lodz (Lodzkie) ---
    "lodz":               ("MPK Lodz",                          "GTFS — Lodz municipal transit (MPK, tram + bus)",       "Lodzkie",              "Lodz"),
    "lodz-lka":           ("Lodzka Kolej Aglomeracyjna (LKA)",  "GTFS — Lodz agglomeration rail (LKA)",                  "Lodzkie",              "Lodz"),
    # --- Lublin (Lubelskie) ---
    "lublin":             ("ZTM Lublin",                        "GTFS — Lublin (ZTM, trolleybus + bus)",                 "Lubelskie",            "Lublin"),
    # --- Olsztyn (Warminsko-Mazurskie) ---
    "olsztyn":            ("ZDZiT Olsztyn",                     "GTFS — Olsztyn (ZDZiT, tram + bus)",                    "Warminsko-Mazurskie",  "Olsztyn"),
    # --- Opole (Opolskie) ---
    "opole":              ("MZK Opole",                         "GTFS — Opole (MZK)",                                    "Opolskie",             "Opole"),
    # --- National rail (PKP family) — operator-wide, no single city ---
    "pkp-ar":             ("Arriva RP",                         "GTFS — Arriva RP (regional rail)",                      None,                   None),
    "pkp-ic":             ("PKP Intercity",                     "GTFS — PKP Intercity (national long-distance rail)",    None,                   None),
    "pkp-kd":             ("Koleje Dolnoslaskie (KD)",          "GTFS — Koleje Dolnoslaskie (Lower Silesia rail)",       "Dolnoslaskie",         None),
    "pkp-km":             ("Koleje Mazowieckie (KM)",           "GTFS — Koleje Mazowieckie (Mazovia rail)",              "Mazowieckie",          None),
    "pkp-kml":            ("Koleje Malopolskie (KML)",          "GTFS — Koleje Malopolskie (Lesser Poland rail)",        "Malopolskie",          None),
    "pkp-ks":             ("Koleje Slaskie (KS)",               "GTFS — Koleje Slaskie (Silesia rail)",                  "Slaskie",              None),
    "pkp-kw":             ("Koleje Wielkopolskie (KW)",         "GTFS — Koleje Wielkopolskie (Greater Poland rail)",     "Wielkopolskie",        None),
    "pkp-lka":            ("Lodzka Kolej Aglomeracyjna (LKA)",  "GTFS — LKA rail (national listing)",                    "Lodzkie",              None),
    "pkp-pr":             ("POLREGIO",                          "GTFS — POLREGIO (national regional rail)",              None,                   None),
    "pkp-rj":             ("Koleje Poludniowe / RegioJet-type",  "GTFS — PKP-family rail (rj)",                           None,                   None),
    "pkp-skmt":           ("SKM Trojmiasto",                    "GTFS — SKM Trojmiasto (Tricity fast urban rail)",       "Pomorskie",            "Gdansk"),
    "pkp-skmw":           ("SKM Warszawa",                      "GTFS — SKM Warszawa (Warsaw fast urban rail)",          "Mazowieckie",          "Warszawa"),
    "pkp-wkd":            ("Warszawska Kolej Dojazdowa (WKD)",  "GTFS — Warszawska Kolej Dojazdowa (WKD)",               "Mazowieckie",          "Warszawa"),
    # --- Poznan (Wielkopolskie) ---
    "poznan":             ("ZTM Poznan / MPK Poznan",           "GTFS — Poznan municipal transit (ZTM/MPK, tram + bus)", "Wielkopolskie",        "Poznan"),
    "poznan-kombus":      ("Kombus (Poznan agglomeration)",     "GTFS — Poznan suburban: Kombus",                        "Wielkopolskie",        "Poznan"),
    "poznan-pks":         ("PKS (Poznan agglomeration)",        "GTFS — Poznan suburban: PKS",                           "Wielkopolskie",        "Poznan"),
    "poznan-sroda":       ("Sroda Wielkopolska transit",        "GTFS — Poznan suburban: Sroda Wielkopolska",            "Wielkopolskie",        "Sroda Wielkopolska"),
    # --- Przemysl (Podkarpackie) ---
    "przemysl":           ("MZK Przemysl",                      "GTFS — Przemysl (MZK)",                                 "Podkarpackie",         "Przemysl"),
    # --- Radom (Mazowieckie) ---
    "radom":              ("MZDiK Radom",                       "GTFS — Radom (MZDiK)",                                  "Mazowieckie",          "Radom"),
    # --- Rybnik / Jastrzebie (Slaskie) ---
    "rybnik":             ("ZTZ Rybnik",                        "GTFS — Rybnik (ZTZ)",                                   "Slaskie",              "Rybnik"),
    "rybnik-jastrzebie":  ("MZK Jastrzebie-Zdroj",              "GTFS — Rybnik/Jastrzebie-Zdroj suburban",               "Slaskie",              "Jastrzebie-Zdroj"),
    # --- Rzeszow (Podkarpackie) ---
    "rzeszow":            ("ZTM Rzeszow",                       "GTFS — Rzeszow (ZTM)",                                  "Podkarpackie",         "Rzeszow"),
    "rzeszow-pks":        ("PKS (Rzeszow agglomeration)",       "GTFS — Rzeszow suburban: PKS",                          "Podkarpackie",         "Rzeszow"),
    # --- Suwalki (Podlaskie) ---
    "suwalki":            ("Miasto Suwalki transit",            "GTFS — Suwalki",                                        "Podlaskie",            "Suwalki"),
    # --- Szczecin (Zachodniopomorskie) ---
    "szczecin":           ("ZDiTM Szczecin",                    "GTFS — Szczecin (ZDiTM, tram + bus)",                   "Zachodniopomorskie",   "Szczecin"),
    "szczecin-goleniow":  ("Gmina Goleniow transit",            "GTFS — Szczecin suburban: Goleniow",                    "Zachodniopomorskie",   "Goleniow"),
    # --- Trojmiasto / Tricity (Pomorskie) ---
    "tricity-gdansk":     ("ZTM Gdansk",                        "GTFS — Gdansk (ZTM, tram + bus)",                       "Pomorskie",            "Gdansk"),
    "tricity-gdynia":     ("ZKM Gdynia",                        "GTFS — Gdynia (ZKM, trolleybus + bus)",                 "Pomorskie",            "Gdynia"),
    # --- Warszawa / Warsaw (Mazowieckie) + suburban operators ---
    "warsaw":             ("ZTM Warszawa (Warszawski Transport Publiczny)", "GTFS — Warsaw municipal transit (ZTM/WTP: bus, tram, metro, SKM)", "Mazowieckie", "Warszawa"),
    "warsaw-dabrowka":    ("Gmina Dabrowka transit",            "GTFS — Warsaw suburban: Dabrowka",                      "Mazowieckie",          "Dabrowka"),
    "warsaw-ferries":     ("Warszawskie promy (ZTM ferries)",   "GTFS — Warsaw ferries (Vistula river crossings)",       "Mazowieckie",          "Warszawa"),
    "warsaw-gpa":         ("Grodziskie Przewozy Autobusowe (GPA)", "GTFS — Warsaw suburban: GPA (Grodzisk)",             "Mazowieckie",          "Grodzisk Mazowiecki"),
    "warsaw-lomianki":    ("Gmina Lomianki (KMLomianki)",       "GTFS — Warsaw suburban: Lomianki",                      "Mazowieckie",          "Lomianki"),
    "warsaw-minsk":       ("Minsk Mazowiecki transit",          "GTFS — Warsaw suburban: Minsk Mazowiecki",              "Mazowieckie",          "Minsk Mazowiecki"),
    "warsaw-otwock":      ("Gmina Otwock transit",              "GTFS — Warsaw suburban: Otwock",                        "Mazowieckie",          "Otwock"),
    "warsaw-pruszkow":    ("Pruszkow transit",                  "GTFS — Warsaw suburban: Pruszkow",                      "Mazowieckie",          "Pruszkow"),
    "warsaw-radzymin":    ("Gmina Radzymin transit",            "GTFS — Warsaw suburban: Radzymin",                      "Mazowieckie",          "Radzymin"),
    "warsaw-sochaczew":   ("Sochaczew transit (ZKM)",           "GTFS — Warsaw suburban: Sochaczew",                     "Mazowieckie",          "Sochaczew"),
    "warsaw-sulejowek":   ("Miasto Sulejowek transit",          "GTFS — Warsaw suburban: Sulejowek",                     "Mazowieckie",          "Sulejowek"),
    "warsaw-zabki":       ("Miasto Zabki transit",              "GTFS — Warsaw suburban: Zabki",                         "Mazowieckie",          "Zabki"),
    # --- Wroclaw (Dolnoslaskie) ---
    "wroclaw":            ("MPK Wroclaw",                       "GTFS — Wroclaw municipal transit (MPK, tram + bus)",    "Dolnoslaskie",         "Wroclaw"),
    "wroclaw-olesnica":   ("Olesnica transit",                 "GTFS — Wroclaw suburban: Olesnica",                     "Dolnoslaskie",         "Olesnica"),
    "wroclaw-polbus":     ("Polbus-PKS (Wroclaw agglomeration)", "GTFS — Wroclaw suburban: Polbus-PKS",                  "Dolnoslaskie",         "Wroclaw"),
}


def load_existing():
    try:
        with open(SRC, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except (FileNotFoundError, ValueError):
        pass
    return []


def fetch_listing():
    """Return the raw Nginx autoindex HTML, or '' on failure (never raises)."""
    req = urllib.request.Request(BASE, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.read().decode("utf-8", "replace")
    except (urllib.error.HTTPError, urllib.error.URLError, OSError, ValueError):
        return ""


def parse_slugs(html):
    """Extract .zip feed slugs from the autoindex, deduped, order-preserving.
    Ignores parent-dir / non-zip anchors and any absolute-URL anchors."""
    slugs = []
    seen = set()
    for href in re.findall(r'href="([^"]+\.zip)"', html, flags=re.IGNORECASE):
        # Autoindex hrefs are bare filenames; guard against path/query noise.
        fname = href.split("/")[-1].split("?")[0]
        if not fname.lower().endswith(".zip"):
            continue
        slug = fname[:-4]  # strip .zip
        if slug and slug not in seen:
            seen.add(slug)
            slugs.append(slug)
    return slugs


def derive_meta(slug):
    """Best-effort metadata for a slug not in SLUGMAP (CDN adds feeds over time)."""
    parts = slug.split("-")
    base = parts[0]
    if base == "pkp":
        provider = "PKP-family rail ({})".format(slug)
        return (provider, "GTFS — Polish rail feed: {}".format(slug), None, None)
    # Title-case the base token as a stand-in city; suburban suffix noted in name.
    city = base.replace("_", " ").title()
    if len(parts) > 1:
        provider = "{} area operator ({})".format(city, "-".join(parts[1:]))
        name = "GTFS — {} area feed: {}".format(city, slug)
    else:
        provider = "{} transit".format(city)
        name = "GTFS — {}".format(city)
    return (provider, name, None, city)


def make_record(slug, provider, name, subdiv, city, producer_url):
    return {
        "id": CC.lower() + "-" + slug,
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
    seen = {
        r.get("producer_url", "").rstrip("/")
        for r in existing
        if isinstance(r, dict) and r.get("producer_url")
    }

    html = fetch_listing()
    slugs = parse_slugs(html)
    if not slugs:
        print("+0 new {cc} feeds".format(cc=CC))
        return

    added = 0
    for slug in slugs:
        producer_url = BASE + slug + ".zip"
        if producer_url.rstrip("/") in seen:
            continue
        if slug in SLUGMAP:
            provider, name, subdiv, city = SLUGMAP[slug]
        else:
            provider, name, subdiv, city = derive_meta(slug)
        rec = make_record(slug, provider, name, subdiv, city, producer_url)
        existing.append(rec)
        seen.add(producer_url.rstrip("/"))
        added += 1

    with open(SRC, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    print("+{n} new {cc} feeds".format(n=added, cc=CC))


if __name__ == "__main__":
    main()
