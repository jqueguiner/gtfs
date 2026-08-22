#!/usr/bin/env python3
"""Build the country/city/agency tree + catalog.csv + README table from a
Mobility-Database dump (scripts/ingest_mdb.py writes data/feeds_full.json)."""
import json, os, re, csv, sys, unicodedata
from collections import defaultdict, Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "feeds_full.json")

CC_NAME = {  # minimal ISO-2 -> name (extend freely)
 'FR':'France','US':'United States','CA':'Canada','JP':'Japan','ES':'Spain','IT':'Italy','GB':'United Kingdom',
 'DE':'Germany','SE':'Sweden','PL':'Poland','AU':'Australia','BR':'Brazil','IN':'India','NL':'Netherlands',
 'BE':'Belgium','CH':'Switzerland','AT':'Austria','PT':'Portugal','IE':'Ireland','FI':'Finland','NO':'Norway',
 'DK':'Denmark','CZ':'Czechia','MX':'Mexico','AR':'Argentina','CL':'Chile','NZ':'New Zealand','ID':'Indonesia',
 'ZA':'South Africa','NG':'Nigeria','GH':'Ghana','EE':'Estonia','LT':'Lithuania','LV':'Latvia','GR':'Greece',
 'HU':'Hungary','RO':'Romania','SK':'Slovakia','SI':'Slovenia','HR':'Croatia','RS':'Serbia','BG':'Bulgaria',
 'LU':'Luxembourg','IS':'Iceland','MT':'Malta','CY':'Cyprus','TR':'Turkey','IL':'Israel','TW':'Taiwan',
 'HK':'Hong Kong','SG':'Singapore','KR':'South Korea','TH':'Thailand','MY':'Malaysia','PH':'Philippines',
}


def slug(s, fallback="unknown"):
    s = (s or "").strip()
    if not s:
        return fallback
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s or fallback


def main():
    feeds = json.load(open(SRC))
    feeds = [f for f in feeds if f["status"] not in ("deprecated", "inactive")
             and (f.get("producer_url") or f.get("hosted_url"))]

    # wipe old country dirs
    for d in os.listdir(ROOT):
        if len(d) == 2 and d.isupper() and os.path.isdir(os.path.join(ROOT, d)):
            import shutil; shutil.rmtree(os.path.join(ROOT, d))

    rows = []
    per_country = defaultdict(lambda: {"feeds": 0, "cities": set(), "agencies": set()})
    for f in feeds:
        cc = (f["cc"] or "XX").upper()
        city = f["city"] or f["subdiv"] or "national"
        agency = f["provider"] or f["name"] or f["id"]
        cslug = slug(city, "national")[:40]
        aslug = (slug(agency, f["id"])[:55] + "-" + f["id"].replace("mdb-", ""))
        d = os.path.join(ROOT, cc, cslug, aslug)
        os.makedirs(d, exist_ok=True)
        manifest = {
            "agency": {"name": agency, "country": cc, "subdivision": f["subdiv"], "city": f["city"] or None},
            "feed": {"format": "gtfs", "url": f["producer_url"] or f["hosted_url"],
                     "mdb_id": f["id"], "license": f["license"] or None},
            "bbox": f["bbox"] or None,
            "source": "mobility-database",
            "status": "active",
        }
        json.dump(manifest, open(os.path.join(d, "feed.json"), "w"), indent=2, ensure_ascii=False)
        rows.append([cc, city, agency, f["producer_url"] or f["hosted_url"], f["id"], f["license"], "active"])
        pc = per_country[cc]
        pc["feeds"] += 1; pc["cities"].add(cslug); pc["agencies"].add(aslug)

    # flat catalog
    os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
    with open(os.path.join(ROOT, "catalog.csv"), "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["country", "city", "agency", "feed_url", "mdb_id", "license", "status"])
        w.writerows(sorted(rows))

    # README with coverage table
    order = sorted(per_country, key=lambda c: (c not in ("FR", "US"), -per_country[c]["feeds"]))
    tot_f = sum(v["feeds"] for v in per_country.values())
    tot_ci = sum(len(v["cities"]) for v in per_country.values())
    lines = []
    lines.append("# gtfs — open public-transport catalog\n")
    lines.append("Every public-transport operator we can find, organised **country → city → operator**, "
                 "each with a `feed.json` (GTFS URL + license + bbox). Scraped from open catalogs + agency/gov "
                 "sites, LLM-normalized when the source isn't already GTFS. Priority: 🇫🇷 France, 🇺🇸 USA.\n")
    lines.append(f"**{tot_f} feeds · {tot_ci} cities · {len(per_country)} countries** · updated automatically.\n")
    lines.append("## Layout\n```\n<COUNTRY>/<city>/<operator>/feed.json\n```\n")
    lines.append("`feed.json` = agency + GTFS url + license + bbox (the exchange format). Flat index: `catalog.csv`.\n")
    lines.append("## Coverage\n")
    lines.append("| Country | Feeds | Cities | Operators |")
    lines.append("|---|--:|--:|--:|")
    for cc in order:
        v = per_country[cc]
        name = CC_NAME.get(cc, cc)
        flag = "".join(chr(0x1F1E6 + ord(x) - 65) for x in cc) if len(cc) == 2 and cc.isalpha() else ""
        lines.append(f"| {flag} {name} | {v['feeds']} | {len(v['cities'])} | {len(v['agencies'])} |")
    lines.append("\n## How it works\n")
    lines.append("`scripts/ingest_mdb.py` pulls the Mobility Database, `scripts/scrape_france.py` adds every "
                 "French feed from transport.data.gouv.fr, `scripts/llm_normalize.py` turns non-GTFS sources "
                 "(PDF/HTML/CSV) into GTFS, `scripts/build_repo.py` regenerates this tree + table. "
                 "See `CONTRIBUTING.md` to add your network.\n")
    open(os.path.join(ROOT, "README.md"), "w").write("\n".join(lines))
    print(f"built {tot_f} feeds, {tot_ci} cities, {len(per_country)} countries")
    print("FR:", per_country.get("FR"), "US feeds:", per_country["US"]["feeds"])


if __name__ == "__main__":
    main()
