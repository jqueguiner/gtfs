# gtfs — open public-transport catalog

Every public-transport operator we can find, organised **country → city → operator**, each with a `feed.json` (GTFS URL + license + bbox). Scraped from open catalogs + agency/gov sites, LLM-normalized when the source isn't already GTFS. Priority: 🇫🇷 France, 🇺🇸 USA.

**7687 feeds · 3098 cities · 89 countries** · updated automatically.

## Layout
```
<COUNTRY>/<city>/<operator>/feed.json
```

`feed.json` = agency + GTFS url + license + bbox (the exchange format). Each operator folder also ships a `fetch.sh` that downloads *that* operator's GTFS to `gtfs.zip` (validates `stops.txt`). `./fetch_all.sh [COUNTRY]` runs them all. Flat index: `catalog.csv`.

## Coverage

| Country | Feeds | Cities | Operators |
|---|--:|--:|--:|
| 🇺🇸 United States | 1650 | 835 | 1650 |
| 🇫🇷 France | 1041 | 791 | 627 |
| 🇯🇵 Japan | 1711 | 497 | 1711 |
| 🇽🇽 XX | 997 | 1 | 997 |
| 🇩🇪 Germany | 501 | 25 | 501 |
| 🇸🇻 SV | 295 | 1 | 295 |
| 🇨🇦 Canada | 158 | 129 | 158 |
| 🇪🇸 Spain | 136 | 94 | 136 |
| 🇮🇹 Italy | 124 | 93 | 124 |
| 🇮🇪 Ireland | 112 | 26 | 112 |
| 🇵🇱 Poland | 109 | 80 | 109 |
| 🇫🇮 Finland | 97 | 19 | 97 |
| 🇸🇪 Sweden | 78 | 45 | 78 |
| 🇱🇹 Lithuania | 73 | 30 | 73 |
| 🇳🇴 Norway | 58 | 24 | 58 |
| 🇬🇧 United Kingdom | 46 | 36 | 46 |
| 🇦🇺 Australia | 44 | 35 | 44 |
| 🇵🇹 Portugal | 38 | 30 | 38 |
| 🇱🇻 Latvia | 35 | 10 | 35 |
| 🇹🇭 Thailand | 32 | 13 | 32 |
| 🇪🇪 Estonia | 28 | 19 | 28 |
| 🇦🇹 Austria | 23 | 13 | 23 |
| 🇹🇷 Turkey | 21 | 19 | 21 |
| 🇷🇴 Romania | 20 | 16 | 20 |
| 🇺🇦 UA | 19 | 16 | 19 |
| 🇮🇳 India | 17 | 14 | 17 |
| 🇲🇾 Malaysia | 16 | 15 | 16 |
| 🇷🇸 Serbia | 14 | 10 | 14 |
| 🇨🇾 Cyprus | 14 | 9 | 14 |
| 🇧🇷 Brazil | 13 | 10 | 13 |
| 🇹🇼 Taiwan | 13 | 7 | 13 |
| 🇳🇿 New Zealand | 12 | 10 | 12 |
| 🇭🇺 Hungary | 11 | 11 | 11 |
| 🇧🇪 Belgium | 9 | 7 | 9 |
| 🇨🇿 Czechia | 8 | 4 | 8 |
| 🇸🇮 Slovenia | 6 | 6 | 6 |
| 🇭🇷 Croatia | 6 | 5 | 6 |
| 🇸🇰 Slovakia | 6 | 5 | 6 |
| 🇲🇩 MD | 6 | 5 | 6 |
| 🇨🇴 CO | 6 | 5 | 6 |
| 🇬🇷 Greece | 4 | 3 | 4 |
| 🇧🇬 Bulgaria | 4 | 4 | 4 |
| 🇨🇭 Switzerland | 4 | 3 | 4 |
| 🇸🇬 Singapore | 4 | 2 | 4 |
| 🇵🇪 PE | 3 | 3 | 3 |
| 🇲🇽 Mexico | 3 | 3 | 3 |
| 🇩🇿 DZ | 3 | 3 | 3 |
| 🇵🇭 Philippines | 3 | 3 | 3 |
| 🇬🇭 Ghana | 3 | 2 | 3 |
| 🇦🇱 AL | 3 | 3 | 3 |
| 🇨🇱 Chile | 3 | 3 | 3 |
| 🇳🇱 Netherlands | 3 | 2 | 3 |
| 🇿🇦 South Africa | 2 | 2 | 2 |
| 🇺🇾 UY | 2 | 2 | 2 |
| 🇲🇨 MC | 2 | 2 | 2 |
| 🇨🇳 CN | 2 | 2 | 2 |
| 🇲🇰 MK | 2 | 2 | 2 |
| 🇷🇺 RU | 2 | 2 | 2 |
| 🇦🇷 Argentina | 2 | 2 | 2 |
| 🇪🇹 ET | 1 | 1 | 1 |
| 🇧🇲 BM | 1 | 1 | 1 |
| 🇲🇦 MA | 1 | 1 | 1 |
| 🇲🇱 ML | 1 | 1 | 1 |
| 🇦🇪 AE | 1 | 1 | 1 |
| 🇦🇲 AM | 1 | 1 | 1 |
| 🇭🇳 HN | 1 | 1 | 1 |
| 🇨🇷 CR | 1 | 1 | 1 |
| 🇸🇦 SA | 1 | 1 | 1 |
| 🇳🇬 Nigeria | 1 | 1 | 1 |
| 🇱🇰 LK | 1 | 1 | 1 |
| 🇮🇱 Israel | 1 | 1 | 1 |
| 🇧🇴 BO | 1 | 1 | 1 |
| 🇬🇱 GL | 1 | 1 | 1 |
| 🇱🇦 LA | 1 | 1 | 1 |
| 🇩🇰 Denmark | 1 | 1 | 1 |
| 🇪🇬 EG | 1 | 1 | 1 |
| 🇹🇳 TN | 1 | 1 | 1 |
| 🇮🇸 Iceland | 1 | 1 | 1 |
| 🇮🇩 Indonesia | 1 | 1 | 1 |
| 🇧🇦 BA | 1 | 1 | 1 |
| 🇲🇪 ME | 1 | 1 | 1 |
| 🇷🇪 RE | 1 | 1 | 1 |
| 🇲🇺 MU | 1 | 1 | 1 |
| 🇨🇮 CI | 1 | 1 | 1 |
| 🇰🇪 KE | 1 | 1 | 1 |
| 🇨🇲 CM | 1 | 1 | 1 |
| 🇵🇷 PR | 1 | 1 | 1 |
| 🇬🇪 GE | 1 | 1 | 1 |
| 🇰🇷 South Korea | 1 | 1 | 1 |

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
