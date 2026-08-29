# gtfs — open public-transport catalog

Every public-transport operator we can find, organised **country → city → operator**, each with a `feed.json` (GTFS URL + license + bbox). Scraped from open catalogs + agency/gov sites, LLM-normalized when the source isn't already GTFS. Priority: 🇫🇷 France, 🇺🇸 USA.

**27912 feeds · 19715 cities · 117 countries** · updated automatically.

## Layout
```
<COUNTRY>/<city>/<operator>/feed.json
```

`feed.json` = agency + GTFS url + license + bbox (the exchange format). Each operator folder also ships a `fetch.sh` that downloads *that* operator's GTFS to `gtfs.zip` (validates `stops.txt`). `./fetch_all.sh [COUNTRY]` runs them all. Flat index: `catalog.csv`.

## Coverage

| Country | Feeds | Cities | Operators |
|---|--:|--:|--:|
| 🇫🇷 France | 3492 | 2926 | 2997 |
| 🇺🇸 United States | 2335 | 1006 | 2335 |
| 🇩🇪 Germany | 7271 | 6737 | 7271 |
| 🇬🇧 United Kingdom | 4033 | 3375 | 4033 |
| 🇯🇵 Japan | 2360 | 602 | 2360 |
| 🇨🇭 Switzerland | 1825 | 1350 | 1825 |
| 🇨🇿 Czechia | 1396 | 1252 | 1396 |
| 🇽🇽 XX | 845 | 1 | 845 |
| 🇳🇱 Netherlands | 725 | 672 | 725 |
| 🇮🇳 India | 364 | 71 | 364 |
| 🇩🇰 Denmark | 359 | 334 | 359 |
| 🇨🇦 Canada | 301 | 152 | 301 |
| 🇸🇻 SV | 295 | 1 | 295 |
| 🇪🇸 Spain | 229 | 110 | 229 |
| 🇮🇹 Italy | 229 | 125 | 229 |
| 🇵🇱 Poland | 173 | 113 | 173 |
| 🇱🇺 Luxembourg | 145 | 140 | 145 |
| 🇧🇷 Brazil | 143 | 78 | 143 |
| 🇸🇪 Sweden | 141 | 46 | 141 |
| 🇮🇪 Ireland | 116 | 27 | 116 |
| 🇫🇮 Finland | 105 | 22 | 105 |
| 🇦🇺 Australia | 99 | 45 | 99 |
| 🇱🇹 Lithuania | 79 | 31 | 79 |
| 🇳🇴 Norway | 64 | 25 | 64 |
| 🇦🇹 Austria | 52 | 15 | 31 |
| 🇵🇹 Portugal | 46 | 34 | 46 |
| 🇱🇻 Latvia | 40 | 11 | 40 |
| 🇹🇭 Thailand | 32 | 13 | 32 |
| 🇪🇪 Estonia | 29 | 19 | 29 |
| 🇭🇷 Croatia | 29 | 22 | 29 |
| 🇸🇰 Slovakia | 28 | 20 | 28 |
| 🇺🇦 UA | 28 | 20 | 28 |
| 🇭🇺 Hungary | 27 | 19 | 27 |
| 🇹🇷 Turkey | 26 | 22 | 26 |
| 🇷🇴 Romania | 24 | 18 | 24 |
| 🇳🇿 New Zealand | 22 | 11 | 22 |
| 🇨🇳 CN | 22 | 13 | 22 |
| 🇸🇮 Slovenia | 20 | 17 | 20 |
| 🇧🇪 Belgium | 20 | 12 | 20 |
| 🇹🇼 Taiwan | 18 | 12 | 18 |
| 🇲🇾 Malaysia | 16 | 15 | 16 |
| 🇷🇸 Serbia | 16 | 11 | 16 |
| 🇨🇾 Cyprus | 15 | 11 | 15 |
| 🇵🇭 Philippines | 14 | 7 | 14 |
| 🇮🇩 Indonesia | 12 | 5 | 12 |
| 🇭🇰 Hong Kong | 11 | 1 | 11 |
| 🇬🇷 Greece | 9 | 5 | 9 |
| 🇨🇴 CO | 9 | 5 | 9 |
| 🇧🇬 Bulgaria | 8 | 5 | 8 |
| 🇵🇪 PE | 7 | 5 | 7 |
| 🇲🇩 MD | 7 | 5 | 7 |
| 🇦🇷 Argentina | 7 | 5 | 7 |
| 🇩🇿 DZ | 6 | 4 | 6 |
| 🇳🇬 Nigeria | 6 | 3 | 6 |
| 🇸🇬 Singapore | 6 | 3 | 6 |
| 🇪🇬 EG | 6 | 4 | 6 |
| 🇨🇱 Chile | 6 | 4 | 6 |
| 🇧🇦 BA | 6 | 3 | 6 |
| 🇰🇪 KE | 6 | 2 | 6 |
| 🇻🇳 VN | 6 | 2 | 6 |
| 🇧🇸 BS | 6 | 1 | 6 |
| 🇲🇽 Mexico | 5 | 5 | 5 |
| 🇲🇦 MA | 5 | 3 | 5 |
| 🇬🇭 Ghana | 5 | 2 | 5 |
| 🇰🇷 South Korea | 5 | 4 | 5 |
| 🇪🇹 ET | 4 | 1 | 4 |
| 🇿🇦 South Africa | 4 | 3 | 4 |
| 🇺🇾 UY | 4 | 2 | 4 |
| 🇮🇱 Israel | 4 | 4 | 4 |
| 🇧🇴 BO | 4 | 3 | 4 |
| 🇲🇰 MK | 3 | 2 | 3 |
| 🇱🇰 LK | 3 | 2 | 3 |
| 🇦🇱 AL | 3 | 3 | 3 |
| 🇷🇺 RU | 3 | 2 | 3 |
| 🇨🇮 CI | 3 | 1 | 3 |
| 🇷🇼 RW | 3 | 1 | 3 |
| 🇻🇪 VE | 3 | 2 | 3 |
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
| 🇯🇪 JE | 1 | 1 | 1 |
| 🇲🇴 MO | 1 | 1 | 1 |

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
