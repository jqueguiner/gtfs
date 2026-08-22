# gtfs — open public-transport catalog

Every public-transport operator we can find, organised **country → city → operator**, each with a `feed.json` (GTFS URL + license + bbox). Scraped from open catalogs + agency/gov sites, LLM-normalized when the source isn't already GTFS. Priority: 🇫🇷 France, 🇺🇸 USA.

**7435 feeds · 3400 cities · 92 countries** · updated automatically.

## Layout
```
<COUNTRY>/<city>/<operator>/feed.json
```

`feed.json` = agency + GTFS url + license + bbox (the exchange format). Each operator folder also ships a `fetch.sh` that downloads *that* operator's GTFS to `gtfs.zip` (validates `stops.txt`). `./fetch_all.sh [COUNTRY]` runs them all. Flat index: `catalog.csv`.

## Coverage

| Country | Feeds | Cities | Operators |
|---|--:|--:|--:|
| 🇺🇸 United States | 1795 | 945 | 1795 |
| 🇫🇷 France | 1107 | 816 | 638 |
| 🇯🇵 Japan | 2235 | 600 | 2235 |
| 🇩🇪 Germany | 503 | 26 | 503 |
| 🇽🇽 XX | 209 | 1 | 209 |
| 🇨🇦 Canada | 166 | 133 | 166 |
| 🇵🇱 Poland | 148 | 107 | 148 |
| 🇪🇸 Spain | 137 | 95 | 137 |
| 🇮🇹 Italy | 127 | 95 | 127 |
| 🇮🇪 Ireland | 112 | 26 | 112 |
| 🇫🇮 Finland | 101 | 22 | 101 |
| 🇸🇪 Sweden | 78 | 45 | 78 |
| 🇱🇹 Lithuania | 76 | 31 | 76 |
| 🇳🇴 Norway | 58 | 24 | 58 |
| 🇬🇧 United Kingdom | 53 | 42 | 53 |
| 🇦🇺 Australia | 50 | 41 | 50 |
| 🇵🇹 Portugal | 39 | 31 | 39 |
| 🇱🇻 Latvia | 37 | 10 | 37 |
| 🇹🇭 Thailand | 32 | 13 | 32 |
| 🇪🇪 Estonia | 28 | 19 | 28 |
| 🇭🇺 Hungary | 24 | 18 | 24 |
| 🇦🇹 Austria | 23 | 13 | 23 |
| 🇷🇴 Romania | 21 | 17 | 21 |
| 🇹🇷 Turkey | 21 | 19 | 21 |
| 🇮🇳 India | 18 | 14 | 18 |
| 🇲🇾 Malaysia | 16 | 15 | 16 |
| 🇷🇸 Serbia | 14 | 10 | 14 |
| 🇧🇷 Brazil | 14 | 11 | 14 |
| 🇳🇿 New Zealand | 13 | 10 | 13 |
| 🇹🇼 Taiwan | 13 | 7 | 13 |
| 🇧🇪 Belgium | 9 | 7 | 9 |
| 🇭🇷 Croatia | 8 | 6 | 8 |
| 🇨🇿 Czechia | 8 | 4 | 8 |
| 🇺🇦 UA | 8 | 7 | 8 |
| 🇸🇮 Slovenia | 7 | 6 | 7 |
| 🇨🇾 Cyprus | 7 | 4 | 7 |
| 🇨🇴 CO | 7 | 5 | 7 |
| 🇸🇰 Slovakia | 6 | 5 | 6 |
| 🇬🇷 Greece | 5 | 4 | 5 |
| 🇧🇬 Bulgaria | 5 | 5 | 5 |
| 🇵🇪 PE | 4 | 4 | 4 |
| 🇲🇽 Mexico | 4 | 4 | 4 |
| 🇨🇭 Switzerland | 4 | 3 | 4 |
| 🇵🇭 Philippines | 4 | 3 | 4 |
| 🇸🇬 Singapore | 4 | 2 | 4 |
| 🇨🇱 Chile | 4 | 4 | 4 |
| 🇲🇩 MD | 4 | 4 | 4 |
| 🇦🇷 Argentina | 4 | 4 | 4 |
| 🇿🇦 South Africa | 3 | 3 | 3 |
| 🇩🇿 DZ | 3 | 3 | 3 |
| 🇬🇭 Ghana | 3 | 2 | 3 |
| 🇦🇱 AL | 3 | 3 | 3 |
| 🇳🇱 Netherlands | 3 | 2 | 3 |
| 🇲🇦 MA | 2 | 2 | 2 |
| 🇺🇾 UY | 2 | 2 | 2 |
| 🇲🇱 ML | 2 | 2 | 2 |
| 🇲🇨 MC | 2 | 2 | 2 |
| 🇦🇪 AE | 2 | 2 | 2 |
| 🇨🇳 CN | 2 | 2 | 2 |
| 🇲🇰 MK | 2 | 2 | 2 |
| 🇮🇸 Iceland | 2 | 2 | 2 |
| 🇷🇪 RE | 2 | 2 | 2 |
| 🇷🇺 RU | 2 | 2 | 2 |
| 🇰🇪 KE | 2 | 2 | 2 |
| 🇪🇹 ET | 1 | 1 | 1 |
| 🇧🇲 BM | 1 | 1 | 1 |
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
| 🇮🇩 Indonesia | 1 | 1 | 1 |
| 🇧🇦 BA | 1 | 1 | 1 |
| 🇲🇪 ME | 1 | 1 | 1 |
| 🇲🇺 MU | 1 | 1 | 1 |
| 🇴🇲 OM | 1 | 1 | 1 |
| 🇨🇮 CI | 1 | 1 | 1 |
| 🇷🇼 RW | 1 | 1 | 1 |
| 🇨🇩 CD | 1 | 1 | 1 |
| 🇨🇲 CM | 1 | 1 | 1 |
| 🇻🇪 VE | 1 | 1 | 1 |
| 🇵🇷 PR | 1 | 1 | 1 |
| 🇰🇷 South Korea | 1 | 1 | 1 |
| 🇻🇳 VN | 1 | 1 | 1 |

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
