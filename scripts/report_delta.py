#!/usr/bin/env python3
"""Compute coverage of data/feeds_full.json, diff against the last snapshot
(data/coverage_snapshot.json), and write an ANALYSED HTML delta report to
/tmp/gtfs_delta.html (subject on stdout), then update the snapshot.

The snapshot stores every feed's key (producer_url) -> [cc, source], so the diff
can explain WHY a number moved: feeds added (by source), feeds removed (source
went offline / URL changed), and feeds RE-PLACED to a different country/city by
the stops.txt geocoder — the usual reason a city/country count wobbles.
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
    cityset = {}
    keys = {}
    for f in act:
        cc = f.get("cc") or "XX"
        city = (f.get("city") or f.get("subdiv") or "national").strip().lower()
        cityset.setdefault(cc, set()).add(city)
        k = (f.get("producer_url") or f.get("hosted_url") or "").rstrip("/")
        if k:
            keys[k] = [cc, f.get("source") or "mdb", city]
    return {
        "feeds": len(act),
        "countries": len([k for k in per if k != "XX"]),
        "cities": sum(len(s) for s in cityset.values()),
        "per_country": dict(per),
        "keys": keys,
    }


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;")


def main():
    cur = coverage()
    prev = json.load(open(SNAP)) if os.path.exists(SNAP) else None

    B = []
    B.append("<div style='font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:660px;margin:auto;color:#202124'>")
    B.append("<h2 style='color:#1a73e8'>🚌 gtfs coverage — hourly</h2>")
    B.append(f"<p><b>{cur['feeds']} feeds · {cur['cities']} cities · {cur['countries']} countries</b></p>")

    if not prev:
        subject = f"gtfs hourly: {cur['feeds']} feeds / {cur['countries']} countries (FIRST SNAPSHOT)"
        B.append("<p style='color:#5f6368'>First snapshot — deltas start next hour.</p>")
    else:
        df = cur["feeds"] - prev["feeds"]
        dco = cur["countries"] - prev["countries"]
        dci = cur["cities"] - prev["cities"]
        col = "#137333" if df > 0 else ("#5f6368" if df == 0 else "#c5221f")
        subject = f"gtfs hourly: {cur['feeds']} feeds / {cur['countries']} countries (Δ {df:+d} feeds · {dco:+d} countries · {dci:+d} cities)"
        B.append(f"<p style='font-size:16px;color:{col}'><b>Δ {df:+d} feeds · {dco:+d} countries · {dci:+d} cities</b> vs last hour</p>")

        pk, ck = prev.get("keys", {}), cur["keys"]
        added = [k for k in ck if k not in pk]
        removed = [k for k in pk if k not in ck]
        moved = [k for k in ck if k in pk and pk[k][0] != ck[k][0]]  # country changed

        # ---- Analysis ----
        B.append("<h3 style='color:#1a73e8;margin-bottom:4px'>Why it changed</h3><ul style='font-size:14px;margin-top:4px'>")
        if added:
            bysrc = Counter(ck[k][1] for k in added)
            src = ", ".join(f"{s} +{n}" for s, n in bysrc.most_common())
            B.append(f"<li><b style='color:#137333'>+{len(added)} feeds added</b> — by source: {esc(src)}</li>")
        if removed:
            bysrc = Counter(pk[k][1] for k in removed)
            byc = Counter(pk[k][0] for k in removed)
            src = ", ".join(f"{s} −{n}" for s, n in bysrc.most_common())
            cc = ", ".join(f"{c} −{n}" for c, n in byc.most_common(6))
            B.append(f"<li><b style='color:#c5221f'>−{len(removed)} feeds removed</b> — source offline / URL changed. "
                     f"By source: {esc(src)}. By country: {esc(cc)}</li>")
        if moved:
            ex = "; ".join(f"{pk[k][0]}→{ck[k][0]}" for k in moved[:6])
            B.append(f"<li><b>{len(moved)} feeds re-placed</b> to a different country by the stops.txt geocoder "
                     f"(shifts city/country counts without changing feed total): {esc(ex)}</li>")
        if not (added or removed or moved):
            B.append("<li style='color:#5f6368'>No feed-level change this hour.</li>")
        B.append("</ul>")

        # ---- Per-country movers ----
        pcp = prev.get("per_country", {})
        movers = []
        for cc in set(list(cur["per_country"]) + list(pcp)):
            if cc == "XX":
                continue
            d = cur["per_country"].get(cc, 0) - pcp.get(cc, 0)
            if d != 0:
                movers.append((cc, cur["per_country"].get(cc, 0), d, cc not in pcp))
        if movers:
            movers.sort(key=lambda x: -abs(x[2]))
            B.append("<table style='border-collapse:collapse;font-size:13px'><tr style='background:#f1f3f4'>"
                     "<td style='padding:6px'><b>Country</b></td><td style='padding:6px'><b>Feeds</b></td><td style='padding:6px'><b>Δ</b></td></tr>")
            for cc, now, d, isnew in movers[:20]:
                c = "#137333" if d > 0 else "#c5221f"
                mark = " 🆕" if isnew else ""
                B.append(f"<tr><td style='padding:5px'>{cc}{mark}</td><td style='padding:5px'>{now}</td>"
                         f"<td style='padding:5px;color:{c}'>{d:+d}</td></tr>")
            B.append("</table>")

    top = sorted(((c, n) for c, n in cur["per_country"].items() if c != "XX"), key=lambda x: -x[1])[:15]
    B.append("<p style='font-size:13px;color:#5f6368'>Top: " + " · ".join(f"{c} {n}" for c, n in top) + "</p>")
    B.append("<p style='font-size:12px'><a href='https://github.com/jqueguiner/gtfs'>github.com/jqueguiner/gtfs</a></p></div>")
    open(OUT, "w").write("\n".join(B))

    json.dump(cur, open(SNAP, "w"), ensure_ascii=False)
    print(subject)


if __name__ == "__main__":
    main()
