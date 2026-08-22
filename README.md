# gtfs — open public-transport catalog

Every public-transport operator we can find, organised **country → city → operator**, each with a `feed.json` (GTFS URL + license + bbox). Scraped from open catalogs + agency/gov sites, LLM-normalized when the source isn't already GTFS. Priority: 🇫🇷 France, 🇺🇸 USA.

**2879 feeds · 2158 cities · 75 countries** · updated automatically.

## Layout
```
<COUNTRY>/<city>/<operator>/feed.json
```

`feed.json` = agency + GTFS url + license + bbox (the exchange format). Flat index: `catalog.csv`.

## Coverage

| Country | Feeds | Cities | Operators |
|---|--:|--:|--:|
| 🇺🇸 United States | 926 | 617 | 926 |
| 🇫🇷 France | 504 | 474 | 504 |
| 🇯🇵 Japan | 588 | 375 | 588 |
| 🇨🇦 Canada | 137 | 118 | 137 |
| 🇪🇸 Spain | 120 | 88 | 120 |
| 🇮🇹 Italy | 91 | 75 | 91 |
| 🇸🇪 Sweden | 54 | 24 | 54 |
| 🇬🇧 United Kingdom | 45 | 35 | 45 |
| 🇵🇱 Poland | 38 | 33 | 38 |
| 🇩🇪 Germany | 35 | 25 | 35 |
| 🇦🇺 Australia | 31 | 27 | 31 |
| 🇪🇪 Estonia | 27 | 18 | 27 |
| 🇵🇹 Portugal | 27 | 26 | 27 |
| 🇫🇮 Finland | 20 | 18 | 20 |
| 🇹🇷 Turkey | 20 | 19 | 20 |
| 🇮🇪 Ireland | 19 | 8 | 19 |
| 🇷🇴 Romania | 17 | 15 | 17 |
| 🇲🇾 Malaysia | 16 | 15 | 16 |
| 🇱🇹 Lithuania | 10 | 10 | 10 |
| 🇳🇿 New Zealand | 10 | 9 | 10 |
| 🇭🇺 Hungary | 10 | 10 | 10 |
| 🇮🇳 India | 9 | 8 | 9 |
| 🇨🇾 Cyprus | 7 | 4 | 7 |
| 🇺🇦 UA | 7 | 6 | 7 |
| 🇸🇮 Slovenia | 6 | 6 | 6 |
| 🇦🇹 Austria | 5 | 5 | 5 |
| 🇷🇸 Serbia | 5 | 4 | 5 |
| 🇧🇷 Brazil | 5 | 4 | 5 |
| 🇨🇿 Czechia | 5 | 4 | 5 |
| 🇸🇰 Slovakia | 5 | 5 | 5 |
| 🇳🇴 Norway | 5 | 4 | 5 |
| 🇱🇻 Latvia | 5 | 4 | 5 |
| 🇭🇷 Croatia | 4 | 3 | 4 |
| 🇸🇬 Singapore | 4 | 2 | 4 |
| 🇧🇬 Bulgaria | 3 | 3 | 3 |
| 🇩🇿 DZ | 3 | 3 | 3 |
| 🇧🇪 Belgium | 3 | 2 | 3 |
| 🇨🇭 Switzerland | 3 | 3 | 3 |
| 🇦🇱 AL | 3 | 3 | 3 |
| 🇵🇪 PE | 2 | 2 | 2 |
| 🇬🇷 Greece | 2 | 2 | 2 |
| 🇲🇽 Mexico | 2 | 2 | 2 |
| 🇲🇨 MC | 2 | 2 | 2 |
| 🇵🇭 Philippines | 2 | 2 | 2 |
| 🇨🇳 CN | 2 | 2 | 2 |
| 🇲🇰 MK | 2 | 2 | 2 |
| 🇨🇱 Chile | 2 | 2 | 2 |
| 🇲🇩 MD | 2 | 2 | 2 |
| 🇨🇴 CO | 2 | 2 | 2 |
| 🇳🇱 Netherlands | 2 | 1 | 2 |
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
| 🇬🇭 Ghana | 1 | 1 | 1 |
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

## How it works

`scripts/ingest_mdb.py` pulls the Mobility Database, `scripts/scrape_france.py` adds every French feed from transport.data.gouv.fr, `scripts/llm_normalize.py` turns non-GTFS sources (PDF/HTML/CSV) into GTFS, `scripts/build_repo.py` regenerates this tree + table. See `CONTRIBUTING.md` to add your network.
