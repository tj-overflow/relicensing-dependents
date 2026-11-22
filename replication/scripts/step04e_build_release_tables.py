"""Step 4e: release tables from the BigQuery extracts (replaces POM fetching in step04b).

Inputs : data/raw/step04/bq_declared.jsonl, bq_versions.csv, bq_parents.jsonl
Resolves declared dependency versions: ${property} from the version's own properties, then its
parent's (one level, from bq_parents); missing versions from dependencyManagement (own, then
parent), including an imported Akka/Pekko BOM.
Outputs (data/raw/step04/): packages.csv, releases.csv, release_deps.csv, resolution_report.json
Same column layout as step04b, so step04c runs unchanged.
"""
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "step04"
WIN_FROM, WIN_TO = "2020-09-07", "2026-11-08"


def family(name):
    if name.startswith(("com.typesafe.akka:", "com.lightbend.akka")):
        return "akka"
    if name.startswith("org.apache.pekko:"):
        return "pekko"
    if name.startswith(("com.typesafe.play:", "org.playframework:")):
        base = re.sub(r"_(2\.1[0-3]|3)$", "", name.split(":", 1)[1])
        core = {"play", "play-server", "play-akka-http-server", "play-pekko-http-server", "play-guice", "play-java",
                "play-test", "play-ahc-ws", "play-ws", "play-netty-server", "play-specs2", "play-logback",
                "play-filters-helpers", "play-cache", "play-jdbc", "play-streams"}
        return "play" if base in core else None
    return None


def load_jsonl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8")]


decl = load_jsonl(RAW / "bq_declared.jsonl")
if (RAW / "bq_declared_pekko.jsonl").exists():  # step04f: Pekko-only packages
    decl += load_jsonl(RAW / "bq_declared_pekko.jsonl")
parents = {(r["package"], r["version"]): r for r in load_jsonl(RAW / "bq_parents.jsonl")}
vers = list(csv.DictReader(open(RAW / "bq_versions.csv", encoding="utf-8")))
if (RAW / "bq_versions_pekko.csv").exists():
    vers += list(csv.DictReader(open(RAW / "bq_versions_pekko.csv", encoding="utf-8")))
pub = {(v["package"], v["version"]): v for v in vers}


def props_of(r):
    return {p["Name"]: p["Value"] for p in (r.get("props") or [])}


def resolve(val, props, depth=0):
    if not val or "${" not in val or depth > 5:
        return val
    return resolve(re.sub(r"\$\{([^}]+)\}", lambda m: props.get(m.group(1), m.group(0)), val), props, depth + 1)


stats = Counter()
rel_rows, dep_rows = [], []
for r in decl:
    key = (r["package"], r["version"])
    v = pub.get(key, {})
    published = (v.get("published") or "")[:10]
    par = parents.get((r.get("parent_name"), r.get("parent_version"))) if r.get("parent_name") else None
    props = {}
    if par:
        props.update(props_of(par))
    props.update(props_of(r))
    props.setdefault("project.version", r["version"])
    dm = {}
    for src in ([par] if par else []) + [r]:
        for x in src.get("dm") or []:
            dm[x["Name"]] = resolve(x["Version"], props)
    rel_rows.append(dict(package=r["package"], version=r["version"], published=published, pom="bq",
                         scm=v.get("source_repo", ""), licences=v.get("licences", "")))
    for x in r.get("deps") or []:
        fam = family(x["Name"])
        if not fam:
            continue
        vv = resolve(x["Version"], props)
        how = "declared"
        if not vv:
            vv = dm.get(x["Name"], "")
            how = "dm"
            if not vv:  # imported BOM of the same family
                for n, bv in dm.items():
                    if family(n) == fam and "bom" in n:
                        vv, how = bv, "bom"
                        break
        if vv and "${" in vv:
            how = "unresolved_property"
        elif not vv:
            how = "missing"
        stats[how] += 1
        g, a = x["Name"].split(":", 1)
        dep_rows.append(dict(package=r["package"], version=r["version"], published=published, family=fam,
                             dep_group=g, dep_artifact=a, dep_version=vv if how not in ("unresolved_property", "missing") else "",
                             scope=(x.get("Scope") or "compile").lower(), optional=str(x.get("Optional", "")).lower(),
                             resolution=how))

# packages
by_pkg = defaultdict(list)
for v in vers:
    by_pkg[v["package"]].append(v)
pk_rows = []
for p, vs in by_pkg.items():
    vs.sort(key=lambda x: x["published"] or "")
    repo = next((x["source_repo"] for x in reversed(vs) if x["source_repo"]), "")
    pk_rows.append(dict(package=p, n_versions=len(vs),
                        n_in_window=sum(1 for x in vs if WIN_FROM <= (x["published"] or "")[:10] <= WIN_TO),
                        first_published=(vs[0]["published"] or "")[:10], last_published=(vs[-1]["published"] or "")[:10],
                        repo=repo, licence_latest=vs[-1]["licences"], note=""))

# releases of candidate packages that declare none of the families (needed for 'removed' and activity)
seen = {(r["package"], r["version"]) for r in rel_rows}
for v in vers:
    k = (v["package"], v["version"])
    if k not in seen:
        rel_rows.append(dict(package=v["package"], version=v["version"], published=(v["published"] or "")[:10],
                             pom="bq_no_family_deps", scm=v.get("source_repo", ""), licences=v.get("licences", "")))


def write(name, rows):
    keys = list(rows[0].keys())
    with open(RAW / name, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


write("packages.csv", pk_rows)
write("releases.csv", rel_rows)
write("release_deps.csv", dep_rows)
rep = dict(declared_versions=len(decl), version_rows=len(vers), packages=len(pk_rows), release_rows=len(rel_rows),
           dep_rows=len(dep_rows), resolution=stats, parents_available=len(parents))
(RAW / "resolution_report.json").write_text(json.dumps(rep, indent=1, default=dict))
print(json.dumps(rep, indent=1, default=dict))
