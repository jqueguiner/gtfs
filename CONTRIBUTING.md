# Contributing a network

Add or fix a transit operator in three ways — pick the easiest.

## 1. You already publish GTFS
Open a PR adding `<COUNTRY>/<city>/<operator>/feed.json`:

```json
{
  "agency": {"name": "Your Transit Co", "country": "FR", "subdivision": "Bretagne", "city": "Rennes"},
  "feed": {"format": "gtfs", "url": "https://your.site/gtfs.zip", "license": "ODbL-1.0"},
  "bbox": {"minimum_latitude": 48.0, "maximum_latitude": 48.2, "minimum_longitude": -1.8, "maximum_longitude": -1.6},
  "source": "operator",
  "status": "active"
}
```
`<COUNTRY>` = ISO-3166-1 alpha-2. `city`/`operator` folders = lowercase-hyphen slug. That's it.

## 2. You publish a schedule, but not GTFS (PDF / web page / CSV)
Open an issue with the link. The `scripts/llm_normalize.py` pipeline converts it
to GTFS (LLM + strict schema) and flags it `"source":"llm-normalized"` with a
confidence score for review before merge.

## 3. It's in an open catalog we should be scraping
Tell us the catalog. Country scrapers live in `scripts/` (`scrape_france.py`
mirrors transport.data.gouv.fr; add `scrape_<cc>.py` on the same pattern —
fetch the catalog API, emit records into `data/feeds_full.json`, rerun
`build_repo.py`).

## Regenerating the tree + coverage table
```bash
MDB_REFRESH_TOKEN=... python3 scripts/ingest_mdb.py   # pull Mobility Database
python3 scripts/scrape_france.py                       # + FR national aggregator
python3 scripts/build_repo.py                          # rebuild tree, catalog.csv, README table
```
CI runs this weekly (`.github/workflows/refresh.yml`) so coverage stays current.

## Priority
🇫🇷 France and 🇺🇸 USA first — most complete, most tested. Everything else welcome.
Data is redistributed under each feed's own license (recorded per `feed.json`).
