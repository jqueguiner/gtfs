# gtfs — open public-transport catalog

Every public-transport operator we can find, organised **country → city → operator**, each with a `feed.json` (GTFS URL + license + bbox). Scraped from open catalogs + agency/gov sites, LLM-normalized when the source isn't already GTFS. Priority: 🇫🇷 France, 🇺🇸 USA.

**26671 feeds · 18944 cities · 115 countries** · updated automatically.

## Layout
```
<COUNTRY>/<city>/<operator>/feed.json
```

`feed.json` = agency + GTFS url + license + bbox (the exchange format). Each operator folder also ships a `fetch.sh` that downloads *that* operator's GTFS to `gtfs.zip` (validates `stops.txt`). `./fetch_all.sh [COUNTRY]` runs them all. Flat index: `catalog.csv`.

## Coverage

| Country | Feeds | Cities | Operators |
|---|--:|--:|--:|
| 🇫🇷 France | 3432 | 2925 | 2962 |
| 🇺🇸 United States | 2325 | 1004 | 2325 |
| 🇩🇪 Germany | 7224 | 6711 | 7224 |
| 🇬🇧 United Kingdom | 4013 | 3367 | 4013 |
| 🇯🇵 Japan | 2357 | 602 | 2357 |
| 🇨🇭 Switzerland | 1825 | 1350 | 1825 |
| 🇨🇿 Czechia | 1395 | 1252 | 1395 |
| 🇽🇽 XX | 847 | 1 | 847 |
| 🇩🇰 Denmark | 358 | 333 | 358 |
| 🇨🇦 Canada | 298 | 151 | 298 |
| 🇸🇻 SV | 295 | 1 | 295 |
| 🇮🇹 Italy | 213 | 122 | 213 |
| 🇪🇸 Spain | 207 | 104 | 207 |
| 🇵🇱 Poland | 171 | 113 | 171 |
| 🇱🇺 Luxembourg | 145 | 140 | 145 |
| 🇧🇷 Brazil | 141 | 78 | 141 |
| 🇸🇪 Sweden | 137 | 46 | 137 |
| 🇮🇪 Ireland | 116 | 27 | 116 |
| 🇫🇮 Finland | 102 | 22 | 102 |
| 🇦🇺 Australia | 99 | 45 | 99 |
| 🇱🇹 Lithuania | 78 | 31 | 78 |
| 🇳🇴 Norway | 60 | 25 | 60 |
| 🇳🇱 Netherlands | 53 | 6 | 53 |
| 🇵🇹 Portugal | 46 | 34 | 46 |
| 🇮🇳 India | 39 | 23 | 39 |
| 🇱🇻 Latvia | 37 | 10 | 37 |
| 🇦🇹 Austria | 33 | 15 | 31 |
| 🇹🇭 Thailand | 32 | 13 | 32 |
| 🇪🇪 Estonia | 29 | 19 | 29 |
| 🇭🇷 Croatia | 29 | 22 | 29 |
| 🇭🇺 Hungary | 27 | 19 | 27 |
| 🇺🇦 UA | 27 | 20 | 27 |
| 🇸🇰 Slovakia | 26 | 20 | 26 |
| 🇹🇷 Turkey | 26 | 22 | 26 |
| 🇷🇴 Romania | 22 | 18 | 22 |
| 🇳🇿 New Zealand | 22 | 11 | 22 |
| 🇨🇳 CN | 22 | 13 | 22 |
| 🇸🇮 Slovenia | 20 | 17 | 20 |
| 🇧🇪 Belgium | 20 | 12 | 20 |
| 🇲🇾 Malaysia | 16 | 15 | 16 |
| 🇹🇼 Taiwan | 16 | 10 | 16 |
| 🇷🇸 Serbia | 14 | 10 | 14 |
| 🇨🇾 Cyprus | 14 | 10 | 14 |
| 🇵🇭 Philippines | 12 | 7 | 12 |
| 🇮🇩 Indonesia | 12 | 5 | 12 |
| 🇬🇷 Greece | 9 | 5 | 9 |
| 🇨🇴 CO | 9 | 5 | 9 |
| 🇧🇬 Bulgaria | 8 | 5 | 8 |
| 🇭🇰 Hong Kong | 8 | 1 | 8 |
| 🇵🇪 PE | 7 | 5 | 7 |
| 🇲🇩 MD | 7 | 5 | 7 |
| 🇩🇿 DZ | 6 | 4 | 6 |
| 🇳🇬 Nigeria | 6 | 3 | 6 |
| 🇨🇱 Chile | 6 | 4 | 6 |
| 🇧🇦 BA | 6 | 3 | 6 |
| 🇦🇷 Argentina | 6 | 5 | 6 |
| 🇰🇪 KE | 6 | 2 | 6 |
| 🇧🇸 BS | 6 | 1 | 6 |
| 🇲🇽 Mexico | 5 | 5 | 5 |
| 🇲🇦 MA | 5 | 3 | 5 |
| 🇬🇭 Ghana | 5 | 2 | 5 |
| 🇸🇬 Singapore | 5 | 3 | 5 |
| 🇪🇹 ET | 4 | 1 | 4 |
| 🇿🇦 South Africa | 4 | 3 | 4 |
| 🇺🇾 UY | 4 | 2 | 4 |
| 🇮🇱 Israel | 4 | 4 | 4 |
| 🇧🇴 BO | 4 | 3 | 4 |
| 🇪🇬 EG | 4 | 3 | 4 |
| 🇻🇳 VN | 4 | 2 | 4 |
| 🇲🇰 MK | 3 | 2 | 3 |
| 🇱🇰 LK | 3 | 2 | 3 |
| 🇦🇱 AL | 3 | 3 | 3 |
| 🇷🇺 RU | 3 | 2 | 3 |
| 🇨🇮 CI | 3 | 1 | 3 |
| 🇷🇼 RW | 3 | 1 | 3 |
| 🇻🇪 VE | 3 | 2 | 3 |
| 🇰🇷 South Korea | 3 | 3 | 3 |
| 🇬🇪 GE | 3 | 1 | 3 |
| 🇰🇿 KZ | 3 | 2 | 3 |
| 🇵🇦 PA | 3 | 2 | 3 |
| 🇹🇿 TZ | 3 | 1 | 3 |
| 🇸🇳 SN | 3 | 1 | 3 |
| 🇵🇾 PY | 3 | 1 | 3 |
| 🇳🇵 NP | 3 | 1 | 3 |
| 🇧🇩 BD | 3 | 1 | 3 |
| 🇲🇲 MM | 3 | 1 | 3 |
| 🇩🇴 DO | 3 | 1 | 3 |
| 🇪🇨 EC | 3 | 1 | 3 |
| 🇵🇰 PK | 3 | 1 | 3 |
| 🇬🇹 GT | 3 | 1 | 3 |
| 🇺🇿 UZ | 3 | 1 | 3 |
| 🇲🇱 ML | 2 | 2 | 2 |
| 🇲🇨 MC | 2 | 2 | 2 |
| 🇦🇪 AE | 2 | 2 | 2 |
| 🇨🇷 CR | 2 | 2 | 2 |
| 🇹🇳 TN | 2 | 2 | 2 |
| 🇮🇸 Iceland | 2 | 2 | 2 |
| 🇷🇪 RE | 2 | 2 | 2 |
| 🇨🇩 CD | 2 | 1 | 2 |
| 🇨🇲 CM | 2 | 2 | 2 |
| 🇰🇭 KH | 2 | 1 | 2 |
| 🇿🇲 ZM | 2 | 1 | 2 |
| 🇧🇲 BM | 1 | 1 | 1 |
| 🇦🇲 AM | 1 | 1 | 1 |
| 🇭🇳 HN | 1 | 1 | 1 |
| 🇸🇦 SA | 1 | 1 | 1 |
| 🇬🇱 GL | 1 | 1 | 1 |
| 🇱🇦 LA | 1 | 1 | 1 |
| 🇲🇪 ME | 1 | 1 | 1 |
| 🇲🇺 MU | 1 | 1 | 1 |
| 🇴🇲 OM | 1 | 1 | 1 |
| 🇵🇷 PR | 1 | 1 | 1 |
| 🇺🇬 UG | 1 | 1 | 1 |
| 🇦🇴 AO | 1 | 1 | 1 |
| 🇽🇰 XK | 1 | 1 | 1 |

## How it works

Feeds are merged from multiple open registries + national access points, then placed to country/city by geohash or a stop coordinate:

- `scripts/ingest_mdb.py` — Mobility Database catalog
- `scripts/scrape_transitland.py` — Transitland Atlas (Interline), ~4000 feeds, superset of MDB
- `scripts/scrape_france.py` — transport.data.gouv.fr (FR national aggregator)
- `scripts/scrape_<cc>.py` — per-country National Access Points (EU-mandated NAPs etc.)
- `scripts/resolve_unplaced.py` — download GTFS, read a stop lat/lon, reverse-geocode any feed still missing a country
- `scripts/llm_normalize.py` — non-GTFS sources (PDF/HTML/CSV) → GTFS via an LLM
- `scripts/build_repo.py` — regenerates this tree, `catalog.csv`, and the table above


`XX` = feeds whose country couldn't be determined yet (unreachable feed / no stops). CI reruns weekly (`.github/workflows/refresh.yml`). See `CONTRIBUTING.md` to add a network.
