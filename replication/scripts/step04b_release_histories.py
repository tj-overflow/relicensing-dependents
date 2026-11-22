"""Step 4b: release histories with declared Akka/Pekko/Play dependencies for candidate dependents.

Input : data/raw/step04/dependent_edges.csv (from step04a)
For each candidate package (excluding Akka's own groups):
  - all versions + publication dates (deps.dev API), plus SOURCE_REPO link and licences of latest version;
  - for versions published 2020-09-07 .. 2026-11-08, the POM from Maven Central, parsed for
    dependencies in Akka (com.typesafe.akka, com.lightbend.akka*), Pekko (org.apache.pekko) and
    Play (com.typesafe.play, org.playframework) groups, with versions resolved from in-POM
    properties, dependencyManagement and up to two parent POMs.
Outputs: data/raw/step04/packages.csv, data/raw/step04/releases.csv (one row per release),
         data/raw/step04/release_deps.csv (one row per release x relevant dependency),
         data/raw/step04/poms/ cache (gzip).
Usage: python -I scripts/step04b_release_histories.py   (resumable via POM cache)
"""
import csv
import gzip
import json
import re
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "step04"
CACHE = RAW / "poms"
CACHE.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "research-script/1.0"}
WIN_FROM, WIN_TO = "2020-09-07", "2026-11-08"
AKKA_G = ("com.typesafe.akka", "com.lightbend.akka")
PEKKO_G = ("org.apache.pekko",)
PLAY_G = ("com.typesafe.play", "org.playframework")
NS = "{http://maven.apache.org/POM/4.0.0}"


def http(url, tries=5, as_json=False):
    for a in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
                b = r.read()
                return json.loads(b) if as_json else b
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                return None
            time.sleep(3 * (a + 1))
        except Exception:
            time.sleep(3 * (a + 1))
    return None


def pom_bytes(g, a, v):
    key = CACHE / f"{g}__{a}__{v}.pom.gz".replace("/", "_")
    if key.exists():
        b = gzip.decompress(key.read_bytes())
        return b or None
    url = f"https://repo1.maven.org/maven2/{g.replace('.', '/')}/{a}/{v}/{a}-{v}.pom"
    b = http(url)
    key.write_bytes(gzip.compress(b or b""))
    return b


def strip(tag):
    return tag.split("}", 1)[-1]


def parse_pom(b):
    """Return dict with properties, deps, depmgmt, parent, licences, scm."""
    try:
        root = ET.fromstring(b)
    except ET.ParseError:
        try:
            root = ET.fromstring(re.sub(rb"<!DOCTYPE[^>]*>", b"", b))
        except ET.ParseError:
            return None

    def find(el, tag):  # single child tag, with or without the POM namespace
        r = el.find(NS + tag)
        return r if r is not None else el.find(tag)

    def text(el, path):
        r = find(el, path)
        return r.text.strip() if r is not None and r.text else None

    props = {}
    pe = find(root, "properties")
    if pe is not None:
        for c in pe:
            if c.text:
                props[strip(c.tag)] = c.text.strip()
    for k, p in (("project.version", "version"), ("project.groupId", "groupId")):
        t = text(root, p)
        if t:
            props[k] = t
    parent = None
    pa = find(root, "parent")
    if pa is not None:
        parent = (text(pa, "groupId"), text(pa, "artifactId"), text(pa, "version"))
        if "project.version" not in props and parent[2]:
            props["project.version"] = parent[2]

    def deps_of(container):
        out = []
        if container is None:
            return out
        for d in container:
            if strip(d.tag) != "dependency":
                continue
            out.append(dict(g=text(d, "groupId"), a=text(d, "artifactId"), v=text(d, "version"),
                            scope=text(d, "scope") or "compile", type=text(d, "type"),
                            optional=text(d, "optional")))
        return out

    deps = deps_of(find(root, "dependencies"))
    dm = find(root, "dependencyManagement")
    dmdeps = deps_of(find(dm, "dependencies")) if dm is not None else []
    lic = []
    le = find(root, "licenses")
    if le is not None:
        for l in le:
            n = text(l, "name")
            if n:
                lic.append(n)
    scm = None
    se = find(root, "scm")
    if se is not None:
        scm = text(se, "url") or text(se, "connection")
    url = text(root, "url")
    return dict(props=props, deps=deps, dm=dmdeps, parent=parent, licences=lic, scm=scm, url=url)


def resolve(val, props, depth=0):
    if not val or "${" not in val or depth > 5:
        return val
    return resolve(re.sub(r"\$\{([^}]+)\}", lambda m: props.get(m.group(1), m.group(0)), val), props, depth + 1)


def effective(g, a, v, depth=0):
    """Merge properties and dependencyManagement from up to two parent POMs."""
    b = pom_bytes(g, a, v)
    if not b:
        return None
    p = parse_pom(b)
    if p is None:
        return None
    if p["parent"] and depth < 2 and all(p["parent"]):
        par = effective(*p["parent"], depth=depth + 1)
        if par:
            merged = dict(par["props"])
            merged.update(p["props"])
            p["props"] = merged
            p["dm"] = p["dm"] + par["dm"]
            p["licences"] = p["licences"] or par["licences"]
            p["scm"] = p["scm"] or par["scm"]
    return p


def group_of(g):
    if g is None:
        return None
    if g.startswith(AKKA_G):
        return "akka"
    if g.startswith(PEKKO_G):
        return "pekko"
    if g.startswith(PLAY_G):
        return "play"
    return None


def main():
    edges = list(csv.DictReader(open(RAW / "dependent_edges.csv", encoding="utf-8")))
    cands = sorted({e["dependent"] for e in edges if not e["dependent"].startswith(AKKA_G)})
    print("candidate packages:", len(cands), flush=True)
    lock = threading.Lock()
    pk_rows, rel_rows, dep_rows = [], [], []

    def do_pkg(name):
        g, a = name.split(":", 1)
        d = http("https://api.deps.dev/v3/systems/maven/packages/" + urllib.parse.quote(name, safe=""), as_json=True)
        if not d:
            with lock:
                pk_rows.append(dict(package=name, n_versions=0, repo="", note="deps.dev not found"))
            return
        vers = sorted([(v.get("publishedAt", "")[:10], v["versionKey"]["version"]) for v in d.get("versions", [])])
        repo = ""
        if vers:
            vi = http("https://api.deps.dev/v3/systems/maven/packages/" + urllib.parse.quote(name, safe="")
                      + "/versions/" + urllib.parse.quote(vers[-1][1], safe=""), as_json=True) or {}
            for l in vi.get("links", []):
                if l.get("label") == "SOURCE_REPO":
                    repo = l.get("url", "")
            lic_latest = ";".join(vi.get("licenses", []))
        else:
            lic_latest = ""
        first_pub = vers[0][0] if vers else ""
        last_pub = vers[-1][0] if vers else ""
        n_in = 0
        for pub, ver in vers:
            if not (WIN_FROM <= pub <= WIN_TO):
                continue
            n_in += 1
            p = effective(g, a, ver)
            if p is None:
                with lock:
                    rel_rows.append(dict(package=name, version=ver, published=pub, pom="missing", scm="", licences=""))
                continue
            props = p["props"]
            dm = {(x["g"], x["a"]): resolve(x["v"], props) for x in p["dm"] if x["g"]}
            rel = dict(package=name, version=ver, published=pub, pom="ok", scm=p["scm"] or p["url"] or "",
                       licences=";".join(p["licences"]))
            out = []
            for x in p["deps"]:
                fam = group_of(resolve(x["g"], props))
                if not fam:
                    continue
                gv = resolve(x["g"], props)
                av = resolve(x["a"], props)
                vv = resolve(x["v"], props) or dm.get((gv, av))
                if not vv:  # BOM import in dependencyManagement
                    for (bg, ba), bv in dm.items():
                        if group_of(bg) == fam and "bom" in (ba or ""):
                            vv = bv
                            break
                out.append(dict(package=name, version=ver, published=pub, family=fam, dep_group=gv,
                                dep_artifact=av, dep_version=vv or "", scope=x["scope"], optional=x["optional"] or ""))
            with lock:
                rel_rows.append(rel)
                dep_rows.extend(out)
        with lock:
            pk_rows.append(dict(package=name, n_versions=len(vers), n_in_window=n_in, first_published=first_pub,
                                last_published=last_pub, repo=repo, licence_latest=lic_latest, note=""))

    with ThreadPoolExecutor(max_workers=8) as ex:
        for i, _ in enumerate(ex.map(do_pkg, cands)):
            if i % 100 == 0:
                print(f"{i}/{len(cands)}", flush=True)

    def write(path, rows):
        if not rows:
            return
        keys = sorted({k for r in rows for k in r})
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(rows)

    write(RAW / "packages.csv", pk_rows)
    write(RAW / "releases.csv", rel_rows)
    write(RAW / "release_deps.csv", dep_rows)
    print("packages", len(pk_rows), "releases", len(rel_rows), "dep rows", len(dep_rows))


if __name__ == "__main__":
    main()
