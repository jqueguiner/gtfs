#!/usr/bin/env python3
"""Integrate a synthesis wave's built feeds into the catalog: filter by quality
gate + dedup against existing llm-normalized feeds, write GTFS, rebuild.
Part of the autonomous coverage-grow loop.

Usage: python3 scripts/integrate_synth.py <built.json>
built.json = the workflow's result {"built":[...]} OR a bare [...] array.
"""
import json, os, sys, subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "feeds_full.json")


def main():
    data = json.load(open(sys.argv[1]))
    built = data.get("built", data) if isinstance(data, dict) else data
    ok = [g for g in built if g and (g.get("confidence") or 0) >= 0.4
          and len(g.get("stops") or []) >= 3 and len(g.get("stop_times") or []) >= 3]
    cat = json.load(open(SRC))
    existing = {(f.get("cc"), f.get("city"), f.get("provider"))
                for f in cat if f.get("source") == "llm-normalized"}
    new = [g for g in ok if (g.get("cc"), g.get("city"), g.get("operator")) not in existing]
    if not new:
        print("no net-new feeds")
        return
    tmp = "/tmp/_synth_integrate.json"
    json.dump(new, open(tmp, "w"), ensure_ascii=False)
    subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "write_synth_gtfs.py"), tmp], check=True)
    subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "build_repo.py")], check=True)
    from collections import Counter
    print("integrated", len(new), "new feeds:", dict(Counter(g.get("cc") for g in new)))


if __name__ == "__main__":
    main()
