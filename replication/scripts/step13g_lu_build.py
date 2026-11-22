"""Step 13g: project-cohort table for the line-launch uptake design.

Risk-set rules as in step13f_lu_feasibility.py. Adds:
  covariates over [L-365, L): releases, artifacts, any _2.13 artifact, project age, days since the last change of the
    highest declared supplier version; Akka only: declares akka-cluster* / akka-persistence*, declares Akka HTTP;
  outcomes: adopt_days (first release in (L, L+365] declaring a stable version >= the new line), act240, act365,
    y1 (adopt within 240 among act240), y1u, y1_365, y2 (A27: new line or Pekko within 365), last_rel_days (censoring);
  Step 15 (R1) additions, for releases in (L, L+h], h = 240, 365: st{h} = declared state of the last release
    (new / old / pekko / none), old{h} = any release declaring the predecessor line, pk{h} = any release declaring Pekko;
  Step 15b (R3) additions, written to separate files so cohorts.csv is unchanged:
    A24 cohort (Akka 2.4.0, 2015-09-30; core set = artifacts with a 2.4.0 version) -> cohorts_a24.csv;
    pre-launch predecessor line per cohort row -> aux_preline.csv; release years per project -> release_years.csv;
  comparison: a project in both comparison cohorts of one period keeps cats-effect only.
Output: outputs/step13/lu/cohorts.csv
"""
import csv
import json
import math
import re
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
R4, R6, O = ROOT / "data/raw/step04", ROOT / "data/raw/step06", ROOT / "outputs/step13/lu"
O.mkdir(parents=True, exist_ok=True)
ALIAS = {"github.com/eclipse/ditto": "github.com/eclipse-ditto/ditto",
         "github.com/balmungsan/neotypes": "github.com/neotypes/neotypes"}
VENDOR = {"lightbend", "akka", "playframework"}
COHORTS = {  # cohort: (library, launch, new line, period, group)
    "A25": ("akka", "2017-04-12", (2, 5), "placebo", "akka"),
    "A26": ("akka", "2019-11-06", (2, 6), "early", "akka"),
    "A27": ("akka", "2022-10-19", (2, 7), "late", "akka"),
    "F21": ("fs2", "2019-11-05", (2, 1), "early", "cmp"),
    "C21": ("cats_effect", "2020-01-31", (2, 1), "early", "cmp"),
    "F34": ("fs2", "2022-11-20", (3, 4), "late", "cmp"),
    "C34": ("cats_effect", "2022-11-13", (3, 4), "late", "cmp"),
}
EXTRA = {"A24": ("akka", "2015-09-30", (2, 4), "placebo2", "akka")}  # Step 15b, section 4
STABLE = re.compile(r"\d+\.\d+\.\d+")


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


core, avail = set(), defaultdict(set)
for r in csv.DictReader(open(R4 / "bq_akka_licences.csv", encoding="utf-8")):
    g, a = r["artifact"].split(":", 1)
    if g == "com.typesafe.akka" and r["version"] in ("2.5.0", "2.6.0", "2.7.0"):
        core.add(base(a))
        if base(a) == "akka-actor":
            avail[vt(r["version"])[:2]].add(sfx(a))
core.discard("akka-http")
core24 = set()
for r in csv.DictReader(open(R4 / "bq_akka_licences.csv", encoding="utf-8")):
    g, a = r["artifact"].split(":", 1)
    if g == "com.typesafe.akka" and r["version"] == "2.4.0":
        core24.add(base(a))
        if base(a) == "akka-actor":
            avail[(2, 4)].add(sfx(a))
core24 = {c for c in core24 if not c.startswith("akka-http")}

# ---------- Akka dependents: release-level records ----------
rel_repo, rel_date = {}, {}
for r in csv.DictReader(open(R4 / "releases.csv", encoding="utf-8")):
    rel_date[(r["package"], r["version"])] = r["published"]
    if r["scm"]:
        rel_repo[r["package"]] = r["scm"]
A = defaultdict(lambda: dict(core=[], play=False, http=False, clpe=False, pekko=False, core24=[], clpe24=False))
for d in csv.DictReader(open(R4 / "release_deps.csv", encoding="utf-8")):
    k = (d["package"], d["version"])
    if d["family"] == "play" or d["dep_group"] in ("com.typesafe.play", "org.playframework"):
        A[k]["play"] = True
    if d["scope"] == "test" or d["optional"] == "true" or not d["dep_version"]:
        continue
    g, a = d["dep_group"], d["dep_artifact"]
    if g == "org.apache.pekko":
        A[k]["pekko"] = True
    if g == "com.typesafe.akka" and base(a).startswith("akka-http"):
        A[k]["http"] = True
    if g == "com.typesafe.akka" and base(a) in core24:
        A[k]["core24"].append((d["dep_version"], sfx(a)))
        if base(a).startswith(("akka-cluster", "akka-persistence")):
            A[k]["clpe24"] = True
    if g == "com.typesafe.akka" and base(a) in core:
        A[k]["core"].append((d["dep_version"], sfx(a)))
        if base(a).startswith(("akka-cluster", "akka-persistence")):
            A[k]["clpe"] = True
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
C = {}
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
    C[(j["package"], j["version"])] = lines
cmp_recs = defaultdict(list)
for (pkg, ver), pub in cvers.items():
    cmp_recs[norm_repo(crepo.get(pkg), pkg)].append((pub, pkg, ver))


def owner(p):
    return p.split("/")[1] if p.startswith("github.com/") else p


def versions(lib, pkg, ver, ck="core"):
    """Declared supplier versions of one release (non-test, non-optional)."""
    if lib == "akka":
        return [v for v, s in A[(pkg, ver)][ck]] if (pkg, ver) in A else []
    return C.get((pkg, ver), {}).get(lib, [])


def days(a, b):
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


rows, rows24, aux = [], [], []
for coh, (lib, L, new, period, group) in {**COHORTS, **EXTRA}.items():
    ck = "core24" if coh == "A24" else "core"
    preline = None
    Ld = date.fromisoformat(L)
    lo, hi = (Ld - timedelta(days=365)).isoformat(), (Ld + timedelta(days=365)).isoformat()
    recs = akka_recs if lib == "akka" else cmp_recs
    for proj, rs in recs.items():
        rs = sorted(rs)
        pre = [x for x in rs if lo <= x[0] < L]
        if not pre:
            continue
        last = {}
        for x in pre:
            last[x[1]] = x
        qual = preadopt = inelig = isplay = overlap = False
        http = clpe = False
        for pub, pkg, ver in last.values():
            if lib == "akka":
                rec = A.get((pkg, ver))
                if not rec or not rec[ck]:
                    continue
                ds = rec[ck]
                top = max(ds, key=lambda z: vt(z[0]))
                if vt(top[0])[:2] >= new:
                    preadopt = True
                elif vt(top[0])[:2] == (new[0], new[1] - 1):
                    if any(s in avail[new] for v, s in ds if vt(v)[:2] == vt(top[0])[:2]):
                        qual = True
                        isplay |= rec["play"]
                        http |= rec["http"]
                        clpe |= rec["clpe24" if ck == "core24" else "clpe"]
                        preline = max(preline or (), vt(top[0])[:2])
                    else:
                        inelig = True
            else:
                ls = C.get((pkg, ver), {})
                vs = ls.get(lib, [])
                if not vs:
                    continue
                overlap |= bool(ls.get("akka_any"))
                t = max(vt(v) for v in vs)[:2]
                if t < new:
                    preline = max(preline or (), t)
                if t >= new:
                    preadopt = True
                elif t[0] == new[0]:
                    qual = True
        if not qual or preadopt or owner(proj) in VENDOR or isplay or overlap:
            continue
        # covariates
        first = rs[0][0]
        seq = [(pub, max((vt(v) for v in versions(lib, pkg, ver, ck)), default=())) for pub, pkg, ver in rs if pub < L]
        seq = [(p, t) for p, t in seq if t]
        chg = None
        for (p0, t0), (p1, t1) in zip(seq, seq[1:]):
            if t1 != t0:
                chg = p1
        since = days(chg or seq[0][0], L) if seq else 0
        # outcomes
        post = [x for x in rs if L < x[0] <= hi]
        adopt = None
        y2 = None
        for pub, pkg, ver in post:
            vs = [v for v in versions(lib, pkg, ver, ck) if STABLE.fullmatch(v) and vt(v)[:2] >= new]
            if vs and adopt is None:
                adopt = days(L, pub)
            if lib == "akka" and (vs or A.get((pkg, ver), {}).get("pekko")) and y2 is None:
                y2 = days(L, pub)
        # declared state of each post-launch release (added in Step 15, R1): new line / old line / pekko / none
        def state(pkg, ver):
            vs = versions(lib, pkg, ver, ck)
            if any(vt(v)[:2] >= new for v in vs):
                return "new"
            if vs:
                return "old"
            if lib == "akka" and A.get((pkg, ver), {}).get("pekko"):
                return "pekko"
            return "none"
        win = {h: [(pub, state(pkg, ver)) for pub, pkg, ver in post if days(L, pub) <= h] for h in (240, 365)}
        extra = {}
        for h, xs in win.items():
            sts = {s_ for _, s_ in xs}
            extra[f"st{h}"] = xs[-1][1] if xs else ""
            extra[f"old{h}"] = int("old" in sts) if xs else ""
            extra[f"pk{h}"] = int("pekko" in sts) if xs else ""
        last_rel = max((days(L, x[0]) for x in post), default=0)
        act240 = int(any(days(L, x[0]) <= 240 for x in post))
        act365 = int(bool(post))
        a240 = int(adopt is not None and adopt <= 240)
        (rows24 if coh == "A24" else rows).append(dict(cohort=coh, library=lib, group=group, period=period, project=proj, owner=owner(proj),
                         releases_pre=len(pre), artifacts_pre=len(last),
                         any_213=int(any(x[1].endswith("_2.13") for x in pre)),
                         age_years=round(days(first, L) / 365.25, 3), days_since_change=since,
                         clpe=int(clpe), http=int(http),
                         act240=act240, act365=act365, adopt_days=adopt if adopt is not None else "",
                         y1=a240 if act240 else "", y1u=a240,
                         y1_365=int(adopt is not None) if act365 else "",
                         y2=(int(y2 is not None) if act365 else "") if coh == "A27" else "",
                         last_rel_days=last_rel, **extra))
        aux.append(dict(cohort=coh, project=proj, pre_line=".".join(map(str, preline)) if preline else ""))

# comparison: a project in both cohorts of one period keeps cats-effect only
ce = {(r["period"], r["project"]) for r in rows if r["library"] == "cats_effect"}
n_drop = sum(1 for r in rows if r["library"] == "fs2" and (r["period"], r["project"]) in ce)
rows = [r for r in rows if not (r["library"] == "fs2" and (r["period"], r["project"]) in ce)]
with open(O / "cohorts.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
cnt = defaultdict(lambda: defaultdict(int))
for r in rows:
    cnt[r["cohort"]]["risk_set"] += 1
    cnt[r["cohort"]]["act240"] += r["act240"]
print(json.dumps({k: dict(v) for k, v in cnt.items()}), "fs2 rows dropped (also cats-effect):", n_drop)

# ---------- Step 15b outputs (separate files; cohorts.csv above is unchanged) ----------
for name, rr in (("cohorts_a24.csv", rows24), ("aux_preline.csv", aux)):
    if rr:
        with open(O / name, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rr[0]))
            w.writeheader()
            w.writerows(rr)
with open(O / "release_years.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["source", "project", "year"])
    for src, recs in (("akka", akka_recs), ("cmp", cmp_recs)):
        for proj, rs in recs.items():
            for y in sorted({x[0][:4] for x in rs}):
                w.writerow([src, proj, y])
print("A24 risk set", len(rows24), "active240", sum(r["act240"] for r in rows24), "core24", sorted(core24))
