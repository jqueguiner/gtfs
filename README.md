# gtfs — open public-transport catalog

Every public-transport operator we can find, organised **country → city → operator**, each with a `feed.json` (GTFS URL + license + bbox). Scraped from open catalogs + agency/gov sites, LLM-normalized when the source isn't already GTFS. Priority: 🇫🇷 France, 🇺🇸 USA.

**5997 feeds · 2807 cities · 83 countries** · updated automatically.

## Layout
```
<COUNTRY>/<city>/<operator>/feed.json
```

`feed.json` = agency + GTFS url + license + bbox (the exchange format). Each operator folder also ships a `fetch.sh` that downloads *that* operator's GTFS to `gtfs.zip` (validates `stops.txt`). `./fetch_all.sh [COUNTRY]` runs them all. Flat index: `catalog.csv`.

## Coverage

| Country | Feeds | Cities | Operators |
|---|--:|--:|--:|
| 🇺🇸 United States | 1645 | 832 | 1645 |
| 🇫🇷 France | 1071 | 793 | 602 |
| 🇽🇽 XX | 1208 | 1 | 1208 |
| 🇯🇵 Japan | 1070 | 382 | 1070 |
| 🇨🇦 Canada | 157 | 128 | 157 |
| 🇪🇸 Spain | 130 | 94 | 130 |
| 🇮🇹 Italy | 104 | 87 | 104 |
| 🇸🇪 Sweden | 54 | 24 | 54 |
| 🇵🇱 Poland | 47 | 42 | 47 |
| 🇬🇧 United Kingdom | 46 | 36 | 46 |
| 🇦🇺 Australia | 44 | 35 | 44 |
| 🇮🇪 Ireland | 37 | 23 | 37 |
| 🇩🇪 Germany | 37 | 25 | 37 |
| 🇵🇹 Portugal | 30 | 29 | 30 |
| 🇪🇪 Estonia | 28 | 19 | 28 |
| 🇫🇮 Finland | 20 | 18 | 20 |
| 🇹🇷 Turkey | 20 | 19 | 20 |
| 🇱🇹 Lithuania | 18 | 17 | 18 |
| 🇷🇴 Romania | 18 | 15 | 18 |
| 🇲🇾 Malaysia | 16 | 15 | 16 |
| 🇳🇿 New Zealand | 12 | 10 | 12 |
| 🇭🇺 Hungary | 11 | 11 | 11 |
| 🇮🇳 India | 10 | 9 | 10 |
| 🇧🇷 Brazil | 9 | 8 | 9 |
| 🇦🇹 Austria | 8 | 8 | 8 |
| 🇷🇸 Serbia | 8 | 5 | 8 |
| 🇺🇦 UA | 8 | 7 | 8 |
| 🇨🇾 Cyprus | 7 | 4 | 7 |
| 🇸🇮 Slovenia | 6 | 6 | 6 |
| 🇭🇷 Croatia | 6 | 5 | 6 |
| 🇨🇿 Czechia | 6 | 4 | 6 |
| 🇳🇴 Norway | 6 | 5 | 6 |
| 🇱🇻 Latvia | 6 | 4 | 6 |
| 🇧🇪 Belgium | 5 | 4 | 5 |
| 🇸🇰 Slovakia | 5 | 5 | 5 |
| 🇬🇷 Greece | 4 | 3 | 4 |
| 🇧🇬 Bulgaria | 4 | 4 | 4 |
| 🇨🇭 Switzerland | 4 | 3 | 4 |
| 🇸🇬 Singapore | 4 | 2 | 4 |
| 🇲🇩 MD | 4 | 4 | 4 |
| 🇲🇽 Mexico | 3 | 3 | 3 |
| 🇩🇿 DZ | 3 | 3 | 3 |
| 🇵🇭 Philippines | 3 | 3 | 3 |
| 🇬🇭 Ghana | 3 | 2 | 3 |
| 🇦🇱 AL | 3 | 3 | 3 |
| 🇨🇱 Chile | 3 | 3 | 3 |
| 🇳🇱 Netherlands | 3 | 2 | 3 |
| 🇵🇪 PE | 2 | 2 | 2 |
| 🇲🇨 MC | 2 | 2 | 2 |
| 🇨🇳 CN | 2 | 2 | 2 |
| 🇲🇰 MK | 2 | 2 | 2 |
| 🇨🇴 CO | 2 | 2 | 2 |
| 🇷🇺 RU | 2 | 2 | 2 |
| 🇦🇷 Argentina | 2 | 2 | 2 |
| 🇪🇹 ET | 1 | 1 | 1 |
| 🇿🇦 South Africa | 1 | 1 | 1 |
| 🇧🇲 BM | 1 | 1 | 1 |
| 🇲🇦 MA | 1 | 1 | 1 |
| 🇺🇾 UY | 1 | 1 | 1 |
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
| 🇲🇺 MU | 1 | 1 | 1 |
| 🇨🇮 CI | 1 | 1 | 1 |
| 🇰🇪 KE | 1 | 1 | 1 |
| 🇨🇲 CM | 1 | 1 | 1 |
| 🇵🇷 PR | 1 | 1 | 1 |

## How it works

`scripts/ingest_mdb.py` pulls the Mobility Database, `scripts/scrape_france.py` adds every French feed from transport.data.gouv.fr, `scripts/llm_normalize.py` turns non-GTFS sources (PDF/HTML/CSV) into GTFS, `scripts/build_repo.py` regenerates this tree + table. See `CONTRIBUTING.md` to add your network.
