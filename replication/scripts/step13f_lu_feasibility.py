"""Step 13f: feasibility counts for the line-launch uptake design.

Counts risk-set sizes only. NO adoption outcome is computed: no release after a launch is inspected for its
declared version. Post-launch activity (any release in the window) is counted, because it fixes the denominator.
Cohorts and rules are those of the paper, Section 5.1.
Inputs: data/raw/step04 (Akka dependents, full history), data/raw/step06 (comparison dependents, full history).
Output: outputs/step13/lu_feasibility.json
"""
import csv
import json
import re
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
R4, R6, O = ROOT / "data/raw/step04", ROOT / "data/raw/step06", ROOT / "outputs/step13"
ALIAS = {"github.com/eclipse/ditto": "github.com/eclipse-ditto/ditto",
         "github.com/balmungsan/neotypes": "github.com/neotypes/neotypes"}
VENDOR = {"lightbend", "akka", "playframework"}
H_MAIN, H_SEC = 240, 365
# cohort: (library, launch date, new line, predecessor rule)
COHORTS = {
    "A25": ("akka", "2017-04-12", (2, 5), "prev"),
    "A26": ("akka", "2019-11-06", (2, 6), "prev"),
    "A27": ("akka", "2022-10-19", (2, 7), "prev"),
    "F21": ("fs2", "2019-11-05", (2, 1), "same_major"),
    "C21": ("cats_effect", "2020-01-31", (2, 1), "same_major"),
    "F34": ("fs2", "2022-11-20", (3, 4), "same_major"),
    "C34": ("cats_effect", "2022-11-13", (3, 4), "same_major"),
}


def norm_repo(u, pkg):
    if u:
        m = re.search(r"github\.com[:/]+([^/\s]+)/([^/\s#?]+)", u)
        if m:
            r = ("github.com/" + m.group(1) + "/" + re.sub(r"\.git$", "", m.group(2))).lower()
            return ALIAS.get(r, r)
    return "maven:" + pkg.split(":")[0].lower()


def vt(v):
    return tuple(int(x) for x in re.findall(r"\d+", v.split("-")[0])[:3]) if v else ()


def base(a):
    return re.sub(r"_(2\.1[0-3]|3)$", "", a)


def sfx(a):
    m = re.search(r"_(2\.1[0-3]|3)$", a)
    return m.group(1) if m else ""


# Akka core = com.typesafe.akka artifacts released in lockstep with akka-actor at x.y.0
core, avail = set(), defaultdict(set)
for r in csv.DictReader(open(R4 / "bq_akka_licences.csv", encoding="utf-8")):
    g, a = r["artifact"].split(":", 1)
    if g == "com.typesafe.akka" and r["version"] in ("2.5.0", "2.6.0", "2.7.0"):
        core.add(base(a))
        if base(a) == "akka-actor":
            avail[vt(r["version"])[:2]].add(sfx(a))
core.discard("akka-http")


def akka_core(name):
    g, a = name.split(":", 1)
    return g == "com.typesafe.akka" and base(a) in core


# ---------- Akka dependents ----------
rel_repo, rel_date = {}, {}
for r in csv.DictReader(open(R4 / "releases.csv", encoding="utf-8")):
    rel_date[(r["package"], r["version"])] = r["published"]
    if r["scm"]:
        rel_repo[r["package"]] = r["scm"]
akka_decl = defaultdict(list)  # release -> [(dep version, dep scala suffix)]
play = set()
for d in csv.DictReader(open(R4 / "release_deps.csv", encoding="utf-8")):
    k = (d["package"], d["version"])
    if d["family"] == "play" or d["dep_group"] in ("com.typesafe.play", "org.playframework"):
        play.add(k)
    if d["scope"] == "test" or d["optional"] == "true" or not d["dep_version"]:
        continue
    if akka_core(d["dep_group"] + ":" + d["dep_artifact"]):
        akka_decl[k].append((d["dep_version"], sfx(d["dep_artifact"])))
akka_recs = defaultdict(list)
for (pkg, ver), pub in rel_date.items():
    if pub and pub >= "2005":
        akka_recs[norm_repo(rel_repo.get(pkg), pkg)].append((pub, pkg, ver))

# ---------- comparison dependents ----------
cvers, crepo = {}, {}
for r in csv.DictReader(open(R6 / "bq_cmp_versions.csv", encoding="utf-8")):
    if r["published"] and r["published"][:4] >= "2005":
        cvers[(r["package"], r["version"])] = r["published"][:10]
    if r["source_repo"]:
        crepo[r["package"]] = r["source_repo"]
cdecl = {}
for l in open(R6 / "bq_cmp_declared.jsonl", encoding="utf-8"):
    j = json.loads(l)
    lines = defaultdict(list)
    for x in j["deps"]:
        v = x.get("Version") or ""
        if (x.get("Scope") or "").lower() == "test" or str(x.get("Optional")).lower() == "true" or not v or "${" in v:
            continue
        g, a = x["Name"].split(":", 1)
        if a.startswith("cats-effect"):
            lines["cats_effect"].append(v)
        elif g == "co.fs2":
            lines["fs2"].append(v)
        elif g.startswith("com.typesafe.akka") or g.startswith("com.lightbend.akka") or g == "org.apache.pekko":
            lines["akka_any"].append(v)
    cdecl[(j["package"], j["version"])] = lines
cmp_recs = defaultdict(list)
for (pkg, ver), pub in cvers.items():
    cmp_recs[norm_repo(crepo.get(pkg), pkg)].append((pub, pkg, ver))


def owner(p):
    return p.split("/")[1] if p.startswith("github.com/") else p


def risk(lib, L, new, rule):
    Ld = date.fromisoformat(L)
    lo = (Ld - timedelta(days=365)).isoformat()
    hm, hs = (Ld + timedelta(days=H_MAIN)).isoformat(), (Ld + timedelta(days=H_SEC)).isoformat()
    recs = akka_recs if lib == "akka" else cmp_recs
    c = defaultdict(int)
    for proj, rs in recs.items():
        pre = sorted(x for x in rs if lo <= x[0] < L)
        if not pre:
            continue
        last = {}
        for x in pre:
            last[x[1]] = x
        qual, preadopt, inelig, isplay, akka_overlap = False, False, False, False, False
        for pub, pkg, ver in last.values():
            if lib == "akka":
                ds = akka_decl.get((pkg, ver), [])
                if not ds:
                    continue
                top = max(ds, key=lambda z: vt(z[0]))
                if vt(top[0])[:2] >= new:
                    preadopt = True
                elif vt(top[0])[:2] == (new[0], new[1] - 1):
                    if any(s in avail[new] for v, s in ds if vt(v)[:2] == vt(top[0])[:2]):
                        qual = True
                        isplay |= (pkg, ver) in play
                    else:
                        inelig = True
            else:
                ls = cdecl.get((pkg, ver), {})
                vs = ls.get(lib, [])
                if not vs:
                    continue
                if ls.get("akka_any"):
                    akka_overlap = True
                t = max(vt(v) for v in vs)[:2]
                if t >= new:
                    preadopt = True
                elif t[0] == new[0]:
                    qual = True
        if not (qual or preadopt or inelig):
            continue
        if preadopt:
            c["excluded_already_on_new_line_or_milestone"] += 1
            continue
        if not qual:
            c["excluded_scala_ineligible"] += 1
            continue
        if owner(proj) in VENDOR:
            c["excluded_vendor"] += 1
            continue
        if isplay:
            c["excluded_play"] += 1
            continue
        if akka_overlap:
            c["excluded_declares_akka"] += 1
            continue
        c["risk_set"] += 1
        post = [x for x in rs if L < x[0] <= hs]
        c["active_240d"] += int(any(x[0] <= hm for x in post))
        c["active_365d"] += int(bool(post))
    return dict(c)


out = {k: dict(library=v[0], launch=v[1], new_line=".".join(map(str, v[2])), **risk(*v)) for k, v in COHORTS.items()}
out["_core_artifacts"] = sorted(core)
out["_akka_actor_scala_suffixes"] = {".".join(map(str, k)): sorted(v) for k, v in avail.items()}
(O / "lu_feasibility.json").write_text(json.dumps(out, indent=1))
for k, v in out.items():
    if not k.startswith("_"):
        print(k, v)
print(out["_akka_actor_scala_suffixes"])
