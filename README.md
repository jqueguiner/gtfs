# gtfs — open public-transport catalog

Every public-transport operator we can find, organised **country → city → operator**, each with a `feed.json` (GTFS URL + license + bbox). Scraped from open catalogs + agency/gov sites, LLM-normalized when the source isn't already GTFS. Priority: 🇫🇷 France, 🇺🇸 USA.

**9489 feeds · 3647 cities · 113 countries** · updated automatically.

## Layout
```
<COUNTRY>/<city>/<operator>/feed.json
```

`feed.json` = agency + GTFS url + license + bbox (the exchange format). Each operator folder also ships a `fetch.sh` that downloads *that* operator's GTFS to `gtfs.zip` (validates `stops.txt`). `./fetch_all.sh [COUNTRY]` runs them all. Flat index: `catalog.csv`.

## Coverage

| Country | Feeds | Cities | Operators |
|---|--:|--:|--:|
| 🇺🇸 United States | 1804 | 951 | 1804 |
| 🇫🇷 France | 1118 | 817 | 648 |
| 🇯🇵 Japan | 2315 | 601 | 2315 |
| 🇬🇧 United Kingdom | 675 | 46 | 675 |
| 🇩🇪 Germany | 528 | 35 | 528 |
| 🇨🇭 Switzerland | 477 | 4 | 477 |
| 🇸🇻 SV | 295 | 1 | 295 |
| 🇮🇹 Italy | 201 | 121 | 201 |
| 🇪🇸 Spain | 200 | 101 | 200 |
| 🇨🇦 Canada | 166 | 133 | 166 |
| 🇵🇱 Poland | 149 | 107 | 149 |
| 🇨🇿 Czechia | 144 | 6 | 144 |
| 🇧🇷 Brazil | 138 | 77 | 138 |
| 🇮🇪 Ireland | 112 | 26 | 112 |
| 🇫🇮 Finland | 101 | 22 | 101 |
| 🇸🇪 Sweden | 78 | 45 | 78 |
| 🇱🇹 Lithuania | 76 | 31 | 76 |
| 🇳🇴 Norway | 58 | 24 | 58 |
| 🇽🇽 XX | 57 | 1 | 57 |
| 🇦🇺 Australia | 50 | 41 | 50 |
| 🇳🇱 Netherlands | 46 | 5 | 46 |
| 🇵🇹 Portugal | 39 | 31 | 39 |
| 🇱🇻 Latvia | 37 | 10 | 37 |
| 🇦🇹 Austria | 32 | 15 | 30 |
| 🇹🇭 Thailand | 32 | 13 | 32 |
| 🇪🇪 Estonia | 28 | 19 | 28 |
| 🇮🇳 India | 28 | 19 | 28 |
| 🇩🇰 Denmark | 27 | 2 | 27 |
| 🇸🇰 Slovakia | 26 | 20 | 26 |
| 🇺🇦 UA | 25 | 20 | 25 |
| 🇭🇺 Hungary | 24 | 18 | 24 |
| 🇭🇷 Croatia | 24 | 21 | 24 |
| 🇷🇴 Romania | 21 | 17 | 21 |
| 🇹🇷 Turkey | 21 | 19 | 21 |
| 🇨🇳 CN | 19 | 12 | 19 |
| 🇸🇮 Slovenia | 18 | 17 | 18 |
| 🇲🇾 Malaysia | 16 | 15 | 16 |
| 🇷🇸 Serbia | 14 | 10 | 14 |
| 🇨🇾 Cyprus | 14 | 10 | 14 |
| 🇳🇿 New Zealand | 13 | 10 | 13 |
| 🇹🇼 Taiwan | 13 | 7 | 13 |
| 🇧🇪 Belgium | 9 | 7 | 9 |
| 🇨🇴 CO | 9 | 5 | 9 |
| 🇵🇪 PE | 7 | 5 | 7 |
| 🇬🇷 Greece | 7 | 5 | 7 |
| 🇵🇭 Philippines | 7 | 3 | 7 |
| 🇲🇩 MD | 7 | 5 | 7 |
| 🇩🇿 DZ | 6 | 4 | 6 |
| 🇳🇬 Nigeria | 6 | 3 | 6 |
| 🇰🇪 KE | 6 | 2 | 6 |
| 🇱🇺 Luxembourg | 6 | 1 | 6 |
| 🇧🇬 Bulgaria | 5 | 5 | 5 |
| 🇲🇽 Mexico | 5 | 5 | 5 |
| 🇲🇦 MA | 5 | 3 | 5 |
| 🇬🇭 Ghana | 5 | 2 | 5 |
| 🇧🇦 BA | 5 | 3 | 5 |
| 🇪🇹 ET | 4 | 1 | 4 |
| 🇿🇦 South Africa | 4 | 3 | 4 |
| 🇸🇬 Singapore | 4 | 2 | 4 |
| 🇧🇴 BO | 4 | 3 | 4 |
| 🇪🇬 EG | 4 | 3 | 4 |
| 🇨🇱 Chile | 4 | 4 | 4 |
| 🇮🇩 Indonesia | 4 | 2 | 4 |
| 🇦🇷 Argentina | 4 | 4 | 4 |
| 🇻🇳 VN | 4 | 2 | 4 |
| 🇲🇰 MK | 3 | 2 | 3 |
| 🇱🇰 LK | 3 | 2 | 3 |
| 🇦🇱 AL | 3 | 3 | 3 |
| 🇨🇮 CI | 3 | 1 | 3 |
| 🇷🇼 RW | 3 | 1 | 3 |
| 🇻🇪 VE | 3 | 2 | 3 |
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
| 🇺🇾 UY | 2 | 2 | 2 |
| 🇲🇱 ML | 2 | 2 | 2 |
| 🇲🇨 MC | 2 | 2 | 2 |
| 🇦🇪 AE | 2 | 2 | 2 |
| 🇨🇷 CR | 2 | 2 | 2 |
| 🇹🇳 TN | 2 | 2 | 2 |
| 🇮🇸 Iceland | 2 | 2 | 2 |
| 🇷🇪 RE | 2 | 2 | 2 |
| 🇷🇺 RU | 2 | 2 | 2 |
| 🇨🇩 CD | 2 | 1 | 2 |
| 🇨🇲 CM | 2 | 2 | 2 |
| 🇰🇭 KH | 2 | 1 | 2 |
| 🇿🇲 ZM | 2 | 1 | 2 |
| 🇧🇲 BM | 1 | 1 | 1 |
| 🇦🇲 AM | 1 | 1 | 1 |
| 🇭🇳 HN | 1 | 1 | 1 |
| 🇸🇦 SA | 1 | 1 | 1 |
| 🇮🇱 Israel | 1 | 1 | 1 |
| 🇬🇱 GL | 1 | 1 | 1 |
| 🇱🇦 LA | 1 | 1 | 1 |
| 🇲🇪 ME | 1 | 1 | 1 |
| 🇲🇺 MU | 1 | 1 | 1 |
| 🇴🇲 OM | 1 | 1 | 1 |
| 🇵🇷 PR | 1 | 1 | 1 |
| 🇰🇷 South Korea | 1 | 1 | 1 |
| 🇬🇪 GE | 1 | 1 | 1 |
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
