"""Step 9h: verify registry releases whose Elasticsearch-family dependency list is empty in the outcome window.

deps.dev occasionally stores an empty requirements record for a release whose POM does declare dependencies
(e.g. org.craftercms:crafter-search-opensearch 4.1.2, 4.1.3, 4.1.8 while 4.1.1-4.3.1 otherwise declare
OpenSearch). An empty family list is read as 'no Elasticsearch/OpenSearch', so such records can turn a
project into 'removed' or drop one side of 'dual'. For every active risk-set project, each release that
enters the outcome window (artifacts released within 6 months of the project's last release on or before
2024-11-11, and likewise for 2025-09-30) and has an empty family list is checked against its POM on Maven
Central (paced, cached, 429-aware). Family dependencies found in the POM are written out with their declared
version (literal or ${property} resolved within the same POM; otherwise empty).
Output: data/raw/step09/empty_record_check.csv (read by step08c when present)
"""
import csv
import json
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data/raw/step09/release_poms"
CACHE.mkdir(parents=True, exist_ok=True)
NS = "{http://maven.apache.org/POM/4.0.0}"
FAM = ("org.elasticsearch", "co.elastic.clients", "org.opensearch", "org.springframework.data:spring-data-elasticsearch",
       "org.springframework.boot:spring-boot-starter-data-elasticsearch")
EVENT = "2021-01-14"


def fetch(g, a, v):
    f = CACHE / f"{g}__{a}__{v}.pom"
    if f.exists():
        return f.read_bytes(), "cached"
    url = f"https://repo1.maven.org/maven2/{g.replace('.', '/')}/{a}/{v}/{a}-{v}.pom"
    wait = 30
    for _ in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "research-script/1.0"}), timeout=30) as r:
                b = r.read()
            f.write_bytes(b)
            time.sleep(1.0)
            return b, "fetched"
        except urllib.error.HTTPError as e:
            if e.code == 404:
                f.write_bytes(b"")
                return b"", "not_found"
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(wait)
                wait = min(wait * 2, 600)
                continue
            break
        except Exception:
            time.sleep(5)
    print("ABORT: fetch failed after retries (Maven Central blocking)", url, flush=True)
    raise SystemExit(3)


def family_deps(b):
    if not b:
        return []
    try:
        root = ET.fromstring(re.sub(rb"<!DOCTYPE[^>]*>", b"", b))
    except ET.ParseError:
        return None

    def t(el, tag):
        r = el.find(NS + tag)
        r = r if r is not None else el.find(tag)
        return r.text.strip() if r is not None and r.text else ""
    props = {}
    pe = root.find(NS + "properties")
    pe = pe if pe is not None else root.find("properties")
    for c in (pe if pe is not None else []):
        if c.text:
            props[c.tag.replace(NS, "")] = c.text.strip()
    ds = root.find(NS + "dependencies")
    ds = ds if ds is not None else root.find("dependencies")
    out = []
    for d in (ds if ds is not None else []):
        name = f"{t(d, 'groupId')}:{t(d, 'artifactId')}"
        if not name.startswith(FAM):
            continue
        v = re.sub(r"\$\{([^}]+)\}", lambda m: props.get(m.group(1), m.group(0)), t(d, "version"))
        out.append(dict(dep=name, dep_version="" if "${" in v else v, scope=(t(d, "scope") or "compile").lower(),
                        optional=t(d, "optional").lower() or "false"))
    return out


fam_rel = defaultdict(set)
for d in csv.DictReader(open(ROOT / "data/raw/step08/es_release_deps.csv", encoding="utf-8")):
    fam_rel[(d["package"], d["version"])].add(d["dep"])
risk = {r["project"] for r in csv.DictReader(open(ROOT / "outputs/step08/es_risk_set.csv", encoding="utf-8"))
        if r["active_post"] == "1"}
pan = defaultdict(list)
for r in csv.DictReader(open(ROOT / "outputs/step08/es_project_panel.csv", encoding="utf-8")):
    if r["project"] in risk and r["published"] >= EVENT:
        pan[r["project"]].append(r)
todo = set()
for p, rs in pan.items():
    for horizon in ("2024-11-11", "2025-09-30"):
        last = {}
        for r in sorted((r for r in rs if r["published"] <= horizon), key=lambda r: r["published"]):
            last[r["package"]] = r
        if not last:
            continue
        pl = max(r["published"] for r in last.values())
        y, m = int(pl[:4]), int(pl[5:7])
        cut = f"{y - (1 if m <= 6 else 0):04d}-{(m - 7) % 12 + 1:02d}{pl[7:10]}"
        for r in last.values():
            if r["published"] >= cut and not fam_rel.get((r["package"], r["version"])):
                todo.add((r["package"], r["version"]))
print("releases to check:", len(todo), flush=True)
rows = []
for i, (pkg, ver) in enumerate(sorted(todo), 1):
    g, a = pkg.split(":")
    b, st = fetch(g, a, ver)
    fd = family_deps(b)
    if fd is None:
        st = "parse_error"
        fd = []
    rows.append(dict(package=pkg, version=ver, pom_status=st, n_family=len(fd),
                     family=json.dumps(fd)))
    if i % 50 == 0:
        print(i, flush=True)
with open(ROOT / "data/raw/step09/empty_record_check.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
print(json.dumps(dict(checked=len(rows), status={s: sum(r["pom_status"] == s for r in rows) for s in {r["pom_status"] for r in rows}},
                      contradicted=sum(r["n_family"] > 0 for r in rows)), indent=1))
