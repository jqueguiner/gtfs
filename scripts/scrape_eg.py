#!/usr/bin/env python3
"""Scraper for Egypt (EG) open-transit GTFS feeds.

Egypt has NO government National Access Point. NTRA / NAT (National Authority
for Tunnels, owner of the Cairo Metro) publish nothing machine-readable. The
de-facto open-data hub is the NGO Transport for Cairo (TfC), a founding partner
of DigitalTransport4Africa (DT4A). TfC GTFS is mirrored in three places, which
this scraper unions (each guarded independently so one dead mirror never aborts
the run):

  (1) TUMI Datahub -- a CKAN instance at hub.tumidata.org exposing the standard
      CKAN API. PRIMARY / most reliable enumerator. We call
        /api/3/action/package_search?q=Egypt%20GTFS   (also q=Cairo, q=Alexandria)
      and, as a fallback, package_show on the two known dataset slugs:
        - gtfs_feed_for_the_formal_and_pratransit_in_the_gcr_the_cairo_metro_cairo (Cairo GCR)
        - gtfs-alexandria (Alexandria)
      For each package we read result.results[i].resources[j].url and keep the
      resources whose format == 'ZIP' (or whose url ends in .zip) -- those are
      the direct GTFS zip downloads.

  (2) TfC GitHub org -- github.com/transportforcairo. SECONDARY. Via the GitHub
      contents API we harvest:
        - Metro-GTFS  (3 Cairo metro lines; ships an Archive.zip at repo root,
          plus the raw GTFS .txt files)
        - Transit---GCR-Digital-Cairo-2017-  (full GCR bus+minibus+paratransit
          +metro feed; the GTFS lives as folders of .txt files with no bundled
          zip, so the direct-download URL we record is the repo *zipball*).
      A repo that already contains a root-level *.zip uses that file's
      download_url; a repo whose GTFS is only loose .txt files uses the codeload
      zipball URL for its default branch.

  (3) DT4A self-hosted GitLab -- git.digitaltransport4africa.org/data/africa/
      {cairo,alexandria}. TERTIARY. Its TLS certificate is EXPIRED, so we
      disable certificate verification for this host only. We enumerate the
      group's projects, walk each repo tree (recursive) for *.zip files, and
      build a raw-blob download URL on the project's default branch.

Only two Egyptian cities have GTFS: Cairo (Greater Cairo Region) and Alexandria.
ALL feeds are Creative Commons CC BY-NC (non-commercial, attribution required),
tagged accordingly. Feeds are somewhat dated (2016-2022).

stdlib only (json, urllib, os, re, ssl). Appends records to data/feeds_full.json
(a JSON array). Dedup is by producer_url (rstrip('/')). Robust: every network
call has a timeout and every source is wrapped so failures are skipped, not
fatal. Prints '+N new EG feeds'.
"""
import json
import os
import re
import ssl
import urllib.request
import urllib.parse
import urllib.error

CC = "EG"
UA = "gtfs-catalog-scraper/1.0"
TIMEOUT = 60
LICENSE = "CC BY-NC 4.0"  # all TfC / DT4A Egypt feeds are non-commercial

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'feeds_full.json')

# --- TUMI Datahub (CKAN) -----------------------------------------------------
CKAN_BASE = "https://hub.tumidata.org/api/3/action"
CKAN_QUERIES = ["Egypt GTFS", "Cairo", "Alexandria"]
# Known dataset slugs (package_show fallback if search is empty / unreachable).
CKAN_KNOWN_SLUGS = [
    "gtfs_feed_for_the_formal_and_pratransit_in_the_gcr_the_cairo_metro_cairo",
    "gtfs-alexandria",
]

# --- TfC GitHub --------------------------------------------------------------
GH_API = "https://api.github.com"
GH_REPOS = [
    # (owner, repo, subdiv, city, provider)
    ("transportforcairo", "Metro-GTFS", "Cairo Governorate", "Cairo",
     "Cairo Metro (National Authority for Tunnels / ECM) - 3 lines"),
    ("transportforcairo", "Transit---GCR-Digital-Cairo-2017-", "Cairo Governorate", "Cairo",
     "GCR combined: Cairo Transport Authority (CTA) bus + minibus + paratransit + Metro"),
]

# --- DT4A self-hosted GitLab (EXPIRED TLS cert) ------------------------------
DT4A_BASE = "https://git.digitaltransport4africa.org"
DT4A_GROUP = "data%2Fafrica"  # url-encoded group path
DT4A_EG_CITIES = {
    "cairo": ("Cairo Governorate", "Cairo"),
    "alexandria": ("Alexandria Governorate", "Alexandria"),
}

# ssl context that ignores cert errors -- used ONLY for the DT4A host.
_INSECURE_CTX = ssl.create_default_context()
_INSECURE_CTX.check_hostname = False
_INSECURE_CTX.verify_mode = ssl.CERT_NONE


def slugify(s):
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def load_existing():
    if not os.path.exists(SRC):
        return []
    try:
        with open(SRC, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (ValueError, OSError):
        return []


def http_json(url, headers=None, insecure=False):
    hdrs = {"User-Agent": UA, "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    ctx = _INSECURE_CTX if insecure else None
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def is_zip_resource(res):
    """A CKAN resource is a GTFS zip if its format is ZIP or its url ends .zip."""
    if not isinstance(res, dict):
        return False
    fmt = (res.get("format") or "").strip().lower()
    url = (res.get("url") or "").strip()
    if not url:
        return False
    if fmt == "zip":
        return True
    return url.lower().split("?")[0].endswith(".zip")


def city_from_text(*texts):
    """Best-effort city classification from title/notes/name."""
    blob = " ".join(t for t in texts if t).lower()
    if "alexandria" in blob:
        return ("Alexandria Governorate", "Alexandria")
    if "cairo" in blob or "gcr" in blob or "greater cairo" in blob:
        return ("Cairo Governorate", "Cairo")
    return (None, None)


# ---------------------------------------------------------------------------
# Source 1: TUMI Datahub (CKAN) -- PRIMARY
# ---------------------------------------------------------------------------
def ckan_packages():
    """Yield unique CKAN package dicts from search queries + known slugs."""
    seen_names = set()
    out = []

    for q in CKAN_QUERIES:
        url = CKAN_BASE + "/package_search?rows=100&q=" + urllib.parse.quote(q)
        try:
            resp = http_json(url)
        except (urllib.error.URLError, ValueError, OSError, ssl.SSLError) as e:
            print("  CKAN: search '%s' failed: %s" % (q, e))
            continue
        result = (resp or {}).get("result") or {}
        for pkg in result.get("results") or []:
            if not isinstance(pkg, dict):
                continue
            nm = pkg.get("name")
            if nm and nm not in seen_names:
                seen_names.add(nm)
                out.append(pkg)

    for slug in CKAN_KNOWN_SLUGS:
        if slug in seen_names:
            continue
        url = CKAN_BASE + "/package_show?id=" + urllib.parse.quote(slug)
        try:
            resp = http_json(url)
        except (urllib.error.URLError, ValueError, OSError, ssl.SSLError) as e:
            print("  CKAN: package_show '%s' failed: %s" % (slug, e))
            continue
        pkg = (resp or {}).get("result")
        if isinstance(pkg, dict):
            nm = pkg.get("name") or slug
            if nm not in seen_names:
                seen_names.add(nm)
                out.append(pkg)
    return out


def scrape_ckan():
    records = []
    for pkg in ckan_packages():
        title = pkg.get("title") or pkg.get("name") or ""
        notes = pkg.get("notes") or ""
        name = pkg.get("name") or slugify(title)
        # Package-level license, else non-commercial default.
        lic = pkg.get("license_title") or pkg.get("license_id") or LICENSE
        subdiv, city = city_from_text(title, notes, name)

        zip_res = [res for res in (pkg.get("resources") or []) if is_zip_resource(res)]
        for i, res in enumerate(zip_res):
            url = res.get("url").strip()
            rname = res.get("name") or title or name
            suffix = "" if len(zip_res) == 1 else "-%d" % (i + 1)
            fid = CC.lower() + "-tumi-" + slugify(name) + suffix
            records.append({
                "id": fid,
                "provider": "Transport for Cairo (TfC) / DigitalTransport4Africa",
                "name": (rname if rname else title) + " (TUMI Datahub)",
                "cc": CC,
                "subdiv": subdiv,
                "city": city,
                "producer_url": url,
                "hosted_url": None,
                "license": lic,
                "bbox": None,
                "status": "active",
                "official": True,
            })
    return records


# ---------------------------------------------------------------------------
# Source 2: TfC GitHub -- SECONDARY
# ---------------------------------------------------------------------------
def gh_default_branch(owner, repo):
    try:
        meta = http_json(GH_API + "/repos/%s/%s" % (owner, repo))
        return meta.get("default_branch") or "master"
    except (urllib.error.URLError, ValueError, OSError, ssl.SSLError):
        return "master"


def gh_has_stops_txt(owner, repo, branch):
    """True if the repo tree contains any stops.txt (i.e. loose GTFS .txt)."""
    try:
        tree = http_json(
            GH_API + "/repos/%s/%s/git/trees/%s?recursive=1" % (owner, repo, branch))
    except (urllib.error.URLError, ValueError, OSError, ssl.SSLError):
        return False
    for t in (tree.get("tree") or []):
        p = (t.get("path") or "").lower()
        if p.endswith("stops.txt"):
            return True
    return False


def scrape_github():
    records = []
    for owner, repo, subdiv, city, provider in GH_REPOS:
        branch = gh_default_branch(owner, repo)
        # 1) Any root-level *.zip -> use its raw download_url directly.
        root_zips = []
        try:
            contents = http_json(GH_API + "/repos/%s/%s/contents/" % (owner, repo))
            if isinstance(contents, list):
                root_zips = [c for c in contents
                             if c.get("type") == "file"
                             and (c.get("name") or "").lower().endswith(".zip")
                             and c.get("download_url")]
        except (urllib.error.URLError, ValueError, OSError, ssl.SSLError) as e:
            print("  GitHub: contents '%s/%s' failed: %s" % (owner, repo, e))

        added_any = False
        for c in root_zips:
            url = c["download_url"]
            fid = CC.lower() + "-gh-" + slugify(repo) + "-" + slugify(c["name"])
            records.append({
                "id": fid,
                "provider": provider,
                "name": "GTFS - %s / %s (TfC GitHub)" % (repo, c["name"]),
                "cc": CC,
                "subdiv": subdiv,
                "city": city,
                "producer_url": url,
                "hosted_url": None,
                "license": LICENSE,
                "bbox": None,
                "status": "active",
                "official": True,
            })
            added_any = True

        # 2) No bundled zip but the repo holds loose GTFS .txt -> record the
        #    codeload zipball of the default branch as the direct download.
        if not added_any and gh_has_stops_txt(owner, repo, branch):
            zipball = GH_API + "/repos/%s/%s/zipball/%s" % (owner, repo, branch)
            fid = CC.lower() + "-gh-" + slugify(repo) + "-zipball"
            records.append({
                "id": fid,
                "provider": provider,
                "name": "GTFS - %s (TfC GitHub, repo zipball @%s)" % (repo, branch),
                "cc": CC,
                "subdiv": subdiv,
                "city": city,
                "producer_url": zipball,
                "hosted_url": None,
                "license": LICENSE,
                "bbox": None,
                "status": "active",
                "official": True,
            })
    return records


# ---------------------------------------------------------------------------
# Source 3: DT4A self-hosted GitLab -- TERTIARY (expired TLS cert)
# ---------------------------------------------------------------------------
def scrape_dt4a():
    records = []
    url = (DT4A_BASE + "/api/v4/groups/" + DT4A_GROUP +
           "/projects?include_subgroups=true&per_page=100")
    try:
        projects = http_json(url, insecure=True)
    except (urllib.error.URLError, ValueError, OSError, ssl.SSLError) as e:
        print("  DT4A: group listing failed: %s" % e)
        return records
    if not isinstance(projects, list):
        return records

    for proj in projects:
        pwn = (proj.get("path_with_namespace") or "")
        tail = pwn.rsplit("/", 1)[-1].lower()
        if tail not in DT4A_EG_CITIES:
            continue
        subdiv, city = DT4A_EG_CITIES[tail]
        branch = proj.get("default_branch") or "master"
        pid = proj.get("id")
        tree_url = (DT4A_BASE + "/api/v4/projects/" + str(pid) +
                    "/repository/tree?recursive=true&per_page=100")
        try:
            tree = http_json(tree_url, insecure=True)
        except (urllib.error.URLError, ValueError, OSError, ssl.SSLError) as e:
            print("  DT4A: tree fetch failed for %s: %s" % (pwn, e))
            continue
        if not isinstance(tree, list):
            continue
        for entry in tree:
            if entry.get("type") != "blob":
                continue
            path = entry.get("path") or ""
            if not path.lower().endswith(".zip"):
                continue
            enc_path = urllib.parse.quote(path, safe="")
            dl = (DT4A_BASE + "/api/v4/projects/" + str(pid) +
                  "/repository/files/" + enc_path + "/raw?ref=" + branch)
            fname = path.rsplit("/", 1)[-1]
            fid = CC.lower() + "-dt4a-" + slugify(city) + "-" + slugify(fname)
            records.append({
                "id": fid,
                "provider": "Transport for Cairo (TfC) / DigitalTransport4Africa",
                "name": "GTFS - %s (%s, DT4A GitLab)" % (fname, city),
                "cc": CC,
                "subdiv": subdiv,
                "city": city,
                "producer_url": dl,
                "hosted_url": None,
                "license": LICENSE,
                "bbox": None,
                "status": "active",
                "official": True,
            })
    return records


def main():
    existing = load_existing()
    seen = set()
    for r in existing:
        pu = r.get("producer_url")
        if pu:
            seen.add(pu.rstrip("/"))

    print("Scraping EG (Egypt) -- no NAP; unioning TUMI Datahub (CKAN) + "
          "TfC GitHub + DT4A GitLab")
    print(" [1] TUMI Datahub (CKAN, primary)")
    ckan = scrape_ckan()
    print("     found %d CKAN feed(s)" % len(ckan))
    print(" [2] TfC GitHub (secondary)")
    gh = scrape_github()
    print("     found %d GitHub feed(s)" % len(gh))
    print(" [3] DT4A GitLab (tertiary, expired-cert)")
    dt4a = scrape_dt4a()
    print("     found %d DT4A feed(s)" % len(dt4a))

    added = 0
    for rec in ckan + gh + dt4a:
        pu = rec.get("producer_url")
        if not pu:
            continue
        key = pu.rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        existing.append(rec)
        added += 1

    if added:
        os.makedirs(os.path.dirname(SRC), exist_ok=True)
        with open(SRC, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

    print("+%d new %s feeds" % (added, CC))


if __name__ == "__main__":
    main()
