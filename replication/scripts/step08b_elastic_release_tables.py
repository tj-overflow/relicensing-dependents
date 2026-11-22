"""Step 8b: Elasticsearch release tables with version resolution.

Inputs : data/raw/step08/bq_declared.jsonl (full: deps, dependencyManagement, filtered properties, parent)
         data/raw/step07_pooled/bq_es_versions.csv (publication dates, source repositories)
Resolution order for a dependency's version: literal -> ${prop} from own properties -> own
dependencyManagement -> parent chain from Maven Central (properties and dependencyManagement, up to
5 levels, including dependencyManagement imports of BOMs, 2 levels). Parent and BOM POMs are fetched
once each from repo1.maven.org (cached in data/raw/step08/poms).
Only releases published 2019-01-01 to 2025-09-30 are resolved (the analysis window).
Outputs: data/raw/step08/es_release_deps.csv, es_resolution_report.json
"""
import csv
import json
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
R8 = ROOT / "data/raw/step08"
CACHE = R8 / "poms"
CACHE.mkdir(parents=True, exist_ok=True)
WIN = ("2019-01-01", "2025-09-30")
NS = "{http://maven.apache.org/POM/4.0.0}"
ES = ("org.elasticsearch", "co.elastic.clients", "org.opensearch", "org.springframework.data:spring-data-elasticsearch",
      "org.springframework.boot:spring-boot-starter-data-elasticsearch")


def fam(name):
    return name.startswith(ES)


FETCH = Counter()


def fetch(g, a, v):
    """Cached POM fetch. 404 is cached as empty; 429/5xx back off (Retry-After or exponential, up to 10 min)
    and are retried; a fetch that still fails is NOT cached and is counted in the report (fetch_failed)."""
    f = CACHE / f"{g}__{a}__{v}.pom"
    if f.exists():
        return f.read_bytes()
    if "${" in g + a + v or not (g and a and v):  # unresolved placeholder coordinates: not fetchable
        FETCH["unresolved_coordinates"] += 1
        return b""
    url = f"https://repo1.maven.org/maven2/{g.replace('.', '/')}/{a}/{v}/{a}-{v}.pom"
    wait = 30
    for i in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "research-script/1.0"}), timeout=30) as r:
                b = r.read()
            f.write_bytes(b)
            FETCH["fetched"] += 1
            FETCH["_consecutive_failed"] = 0
            time.sleep(1.0)  # pacing: at most 1 request per second, one connection
            return b
        except urllib.error.HTTPError as e:
            if e.code == 404:
                f.write_bytes(b"")
                FETCH["not_found"] += 1
                return b""
            if e.code in (429, 500, 502, 503, 504):
                ra = e.headers.get("Retry-After") if e.headers else None
                FETCH[f"http_{e.code}"] += 1
                time.sleep(int(ra) if ra and ra.isdigit() else wait)
                wait = min(wait * 2, 600)
                continue
            FETCH[f"http_{e.code}"] += 1
            FETCH["fetch_failed_other"] += 1  # e.g. 403 on a malformed path: not a block
            print("FETCH FAILED", url, e.code, flush=True)
            return b""
        except Exception as e:
            last = repr(e)[:200]
            time.sleep(5)
    FETCH["fetch_failed"] += 1
    FETCH["_consecutive_failed"] += 1
    print("FETCH FAILED", url, locals().get("last"), flush=True)
    if FETCH["_consecutive_failed"] >= 2:  # Maven Central is blocking: stop instead of degrading the output
        print("ABORT: repeated fetch failures (Maven Central blocking)", dict(FETCH), flush=True)
        sys.exit(3)
    return b""


def parse(b):
    if not b:
        return None
    try:
        root = ET.fromstring(re.sub(rb"<!DOCTYPE[^>]*>", b"", b))
    except ET.ParseError:
        return None

    def find(el, tag):
        r = el.find(NS + tag)
        return r if r is not None else el.find(tag)

    def text(el, tag):
        r = find(el, tag)
        return r.text.strip() if r is not None and r.text else None

    props = {}
    pe = find(root, "properties")
    if pe is not None:
        for c in pe:
            if c.text:
                props[c.tag.replace(NS, "")] = c.text.strip()
    ver = text(root, "version")
    par = find(root, "parent")
    parent = (text(par, "groupId"), text(par, "artifactId"), text(par, "version")) if par is not None else None
    if ver is None and parent:
        ver = parent[2]
    if ver:
        props.setdefault("project.version", ver)
    dm = []
    dme = find(root, "dependencyManagement")
    if dme is not None:
        ds = find(dme, "dependencies")
        for d in (ds if ds is not None else []):
            dm.append(dict(name=f"{text(d, 'groupId')}:{text(d, 'artifactId')}", v=text(d, "version"),
                           scope=text(d, "scope"), type=text(d, "type")))
    return dict(props=props, dm=dm, parent=parent)


def sub(v, props, depth=0):
    if not v or "${" not in v or depth > 6:
        return v
    return sub(re.sub(r"\$\{([^}]+)\}", lambda m: props.get(m.group(1), m.group(0)), v), props, depth + 1)


@lru_cache(maxsize=None)
def effective(g, a, v, depth=0):
    """Properties and managed versions of a POM including its parents and imported BOMs."""
    p = parse(fetch(g, a, v))
    if p is None:
        return ({}, {}, {}, {})
    props, managed, psrc, msrc = {}, {}, {}, {}
    if p["parent"] and all(p["parent"]) and depth < 5:
        pp, pm, ps, ms = effective(*p["parent"], depth=depth + 1)
        props.update(pp)
        managed.update(pm)
        psrc.update(ps)
        msrc.update(ms)
    props.update(p["props"])
    psrc.update({k: f"{g}:{a}" for k in p["props"]})
    for d in p["dm"]:
        dv = sub(d["v"], props)
        if d["scope"] == "import" and d["type"] == "pom" and dv and "${" not in dv and depth < 7:
            g2, a2 = d["name"].split(":")
            bp, bm, bps, bms = effective(g2, a2, dv, depth=depth + 2)
            for k, x in bm.items():
                if k not in managed:
                    managed[k], msrc[k] = x, bms.get(k, f"{g2}:{a2}")
        elif dv:
            managed[d["name"]], msrc[d["name"]] = dv, f"{g}:{a}"
    return (props, {k: sub(x, props) for k, x in managed.items()}, psrc, msrc)


pub = {}
for r in csv.DictReader(open(ROOT / "data/raw/step07_pooled/bq_es_versions.csv", encoding="utf-8")):
    pub[(r["package"], r["version"])] = (r["published"] or "")[:10]
stats = Counter()
rows = []
n = 0
for line in open(R8 / "bq_declared.jsonl", encoding="utf-8"):
    j = json.loads(line)
    d0 = pub.get((j["package"], j["version"]), "")
    if not d0 or not (WIN[0] <= d0 <= WIN[1]):
        continue
    deps = [x for x in (j.get("deps") or []) if fam(x["Name"])]
    if not deps:
        stats["no_family_deps"] += 1
        continue
    props = {p["Name"]: p["Value"] for p in (j.get("props") or [])}
    props.setdefault("project.version", j["version"])
    own_dm = {x["Name"]: sub(x["Version"], props) for x in (j.get("dm") or []) if x.get("Version")}
    par_props, par_dm = None, None
    for x in deps:
        v, how = sub(x.get("Version") or "", props), "literal_or_own"
        src = ""  # POM (groupId:artifactId) in the parent chain or an imported BOM that supplied the version
        if not v and x["Name"] in own_dm:
            v, how = own_dm[x["Name"]], "own_dm"
        if (not v or "${" in v) and j.get("parent_name"):
            if par_props is None:
                g, a = j["parent_name"].split(":")
                par_props, par_dm, par_psrc, par_msrc = effective(g, a, j["parent_version"])
            allp = dict(par_props)
            allp.update(props)
            if not v:
                v, how = sub(par_dm.get(x["Name"], ""), allp), "parent_dm"
                src = par_msrc.get(x["Name"], "")
            else:
                v, how = sub(x["Version"], allp), "parent_props"
                refs = [k for k in re.findall(r"\$\{([^}]+)\}", x["Version"]) if k not in props and k in par_psrc]
                src = par_psrc[refs[0]] if refs else ""
        if not v:
            how = "missing"
        elif "${" in v:
            how, v = "unresolved_property", ""
        stats[how] += 1
        rows.append(dict(package=j["package"], version=j["version"], published=d0, dep=x["Name"], dep_version=v,
                         scope=(x.get("Scope") or "compile").lower(), optional=str(x.get("Optional")).lower(),
                         resolution=how, resolved_from=src if how in ("parent_dm", "parent_props") else ""))
    n += 1
    if n % 5000 == 0:
        print(n, dict(stats), flush=True)
with open(R8 / "es_release_deps.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
tot = sum(v for k, v in stats.items() if k != "no_family_deps")
rep = dict(releases_in_window=n, dep_rows=len(rows), resolution=dict(stats),
           share={k: round(v / tot, 3) for k, v in stats.items() if k != "no_family_deps"},
           parent_poms_cached=len(list(CACHE.glob("*.pom"))), fetch_stats=dict(FETCH))
(R8 / "es_resolution_report.json").write_text(json.dumps(rep, indent=1))
print(json.dumps(rep, indent=1))
