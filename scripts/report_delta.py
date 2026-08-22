#!/usr/bin/env python3
"""Compute coverage of data/feeds_full.json, diff against the last snapshot
(data/coverage_snapshot.json), write an HTML report to /tmp/gtfs_delta.html and
a one-line subject to stdout, then update the snapshot.

Used by the hourly cron (agent/hourly_report.sh) to email coverage deltas.
"""
import json, os
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "feeds_full.json")
SNAP = os.path.join(ROOT, "data", "coverage_snapshot.json")
OUT = os.environ.get("DELTA_HTML", "/tmp/gtfs_delta.html")


def coverage():
    d = json.load(open(SRC))
    act = [f for f in d if f.get("status") not in ("deprecated", "inactive")
           and (f.get("producer_url") or f.get("hosted_url"))]
    per = Counter(f.get("cc") or "XX" for f in act)
    cities = Counter()
    for f in act:
        c = f.get("cc") or "XX"
        city = (f.get("city") or f.get("subdiv") or "").strip().lower()
        if city:
            cities[c] += 0  # placeholder; count distinct below
    # distinct cities per country
    cityset = {}
    for f in act:
        c = f.get("cc") or "XX"
        city = (f.get("city") or f.get("subdiv") or "").strip().lower()
        cityset.setdefault(c, set()).add(city or "national")
    return {
        "feeds": len(act),
        "countries": len([k for k in per if k != "XX"]),
        "cities": sum(len(s) for s in cityset.values()),
        "per_country": dict(per),
        "cities_per_country": {k: len(v) for k, v in cityset.items()},
    }


def main():
    cur = coverage()
    prev = json.load(open(SNAP)) if os.path.exists(SNAP) else None

    d_feeds = cur["feeds"] - (prev["feeds"] if prev else 0)
    d_countries = cur["countries"] - (prev["countries"] if prev else 0)
    d_cities = cur["cities"] - (prev["cities"] if prev else 0)

    # per-country deltas
    pc_prev = (prev or {}).get("per_country", {})
    rows = []
    for cc in sorted(cur["per_country"], key=lambda k: -cur["per_country"][k]):
        if cc == "XX":
            continue
        now = cur["per_country"][cc]
        was = pc_prev.get(cc, 0)
        dc = now - was
        if dc != 0 or not prev:
            rows.append((cc, now, dc, was == 0 and prev is not None))
    new_countries = [cc for cc in cur["per_country"]
                     if cc != "XX" and cc not in pc_prev] if prev else []

    base = "FIRST SNAPSHOT" if not prev else f"Δ {d_feeds:+d} feeds · {d_countries:+d} countries · {d_cities:+d} cities"
    subject = f"gtfs hourly: {cur['feeds']} feeds / {cur['countries']} countries ({base})"

    changed = [r for r in rows if r[2] != 0]
    body = [f"<div style='font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:640px;margin:auto;color:#202124'>"]
    body.append(f"<h2 style='color:#1a73e8'>🚌 gtfs coverage — hourly</h2>")
    body.append(f"<p><b>{cur['feeds']} feeds · {cur['cities']} cities · {cur['countries']} countries</b></p>")
    if prev:
        col = "#137333" if d_feeds > 0 else ("#5f6368" if d_feeds == 0 else "#c5221f")
        body.append(f"<p style='font-size:16px;color:{col}'><b>{base}</b> since last hour</p>")
        if new_countries:
            body.append(f"<p style='font-size:14px'>🆕 new countries: <b>{', '.join(new_countries)}</b></p>")
        if changed:
            body.append("<table style='border-collapse:collapse;font-size:13px'><tr style='background:#f1f3f4'>"
                        "<td style='padding:6px'><b>Country</b></td><td style='padding:6px'><b>Feeds</b></td>"
                        "<td style='padding:6px'><b>Δ</b></td></tr>")
            for cc, now, dc, isnew in changed:
                mark = " 🆕" if isnew else ""
                col = "#137333" if dc > 0 else "#c5221f"
                body.append(f"<tr><td style='padding:5px'>{cc}{mark}</td><td style='padding:5px'>{now}</td>"
                            f"<td style='padding:5px;color:{col}'>{dc:+d}</td></tr>")
            body.append("</table>")
        else:
            body.append("<p style='font-size:14px;color:#5f6368'>No coverage change this hour.</p>")
    top = sorted(((c, n) for c, n in cur["per_country"].items() if c != "XX"), key=lambda x: -x[1])[:15]
    body.append("<p style='font-size:13px;color:#5f6368'>Top: " +
                " · ".join(f"{c} {n}" for c, n in top) + "</p>")
    body.append("<p style='font-size:12px'><a href='https://github.com/jqueguiner/gtfs'>github.com/jqueguiner/gtfs</a></p></div>")
    open(OUT, "w").write("\n".join(body))

    json.dump(cur, open(SNAP, "w"), ensure_ascii=False)
    print(subject)


if __name__ == "__main__":
    main()
