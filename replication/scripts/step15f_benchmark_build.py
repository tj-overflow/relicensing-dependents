"""Step 15f (R4, C1): risk sets of the non-competing benchmark libraries.

For each library in outputs/step15/r4_candidates.json["extract"] and each window (early, late), the launch L is the
first stable x.y.0 in that window (r4_candidates.json["launches"]). Risk set and outcomes follow the comparison
branch of step13g_lu_build.py exactly:
  a project (normalised source repository) enters if it released in [L-365, L), its last release of each package in
  that window declares the library (non-test, non-optional, literal version) on the predecessor line (same major,
  below the new line), none declares the new line or above (pre-adopters out), and none declares Akka/Pekko.
  Vendor projects are out: owners of the source repositories of packages in the library's own group id.
Outcomes: adopt_days (first release in (L, L+365] declaring a stable version >= new line), act240, act365, old240/365.
Then rule 4: a library qualifies if both windows have >= 30 projects active within 240 days; qualifying
libraries are ranked by early risk-set size, the top 5 kept, and a project in several kept risk sets of one period
stays in the largest library's set.
Outputs: outputs/step15/bench_cohorts.csv, outputs/step15/r4_benchmarks.json
"""
import csv
import json
import math
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW, O = ROOT / "data/raw/step15", ROOT / "outputs/step15"
head = (ROOT / "scripts/step13g_lu_build.py").read_text(encoding="utf-8").split("\ncore, avail = set()")[0]
ns = {"__file__": str(ROOT / "scripts/step13g_lu_build.py")}
exec(head, ns)
norm_repo, vt, STABLE, SFX_RE = ns["norm_repo"], ns["vt"], ns["STABLE"], r"_(2\.1[0-3]|3)$"
import re  # noqa: E402

cand = json.loads((O / "r4_candidates.json").read_text())
LIBS = cand["extract"]
LAUNCH = {x["library"]: x for x in cand["launches"] if x["library"] in LIBS}


def raw_open(path):
    """Open a raw extract, or its .gz copy (the replication package ships large extracts gzipped)."""
    import gzip
    path = Path(path)
    if path.exists():
        return open(path, encoding="utf-8")
    return gzip.open(str(path) + ".gz", "rt", encoding="utf-8")


def lib_of(name):
    return re.sub(SFX_RE, "", name)


def owner(p):
    return p.split("/")[1] if p.startswith("github.com/") else p


# ---- releases ----
pub, repo = {}, {}
for r in csv.DictReader(raw_open(RAW / "bench_versions.csv")):
    if r["published"] and r["published"][:4] >= "2005":
        pub[(r["package"], r["version"])] = r["published"][:10]
    if r["source_repo"]:
        repo[r["package"]] = r["source_repo"]
DEC = {}
for line in raw_open(RAW / "bench_declared.jsonl"):
    j = json.loads(line)
    lv, ak = defaultdict(list), False
    for x in j["deps"]:
        v = x.get("Version") or ""
        if (x.get("Scope") or "").lower() == "test" or str(x.get("Optional")).lower() == "true" or not v or "${" in v:
            continue
        n = x["Name"]
        if n.startswith(("com.typesafe.akka:", "com.lightbend.akka", "org.apache.pekko:")):
            ak = True
        else:
            lv[lib_of(n)].append(v)
    DEC[(j["package"], j["version"])] = (lv, ak)
recs = defaultdict(list)
for (pkg, ver), p in pub.items():
    recs[norm_repo(repo.get(pkg), pkg)].append((p, pkg, ver))
for k in recs:
    recs[k].sort()
# vendor owners: most common owner among packages in the library's own group id
vend = {}
for lib in LIBS:
    g = lib.split(":")[0]
    c = Counter(owner(norm_repo(repo.get(p), p)) for p in {k[0] for k in pub} if p.split(":")[0] == g)
    vend[lib] = {o for o, _ in c.most_common(1)}


def days(a, b):
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


rows = []
for lib in LIBS:
    for period in ("early", "late"):
        Lx = LAUNCH[lib]
        L = Lx[f"{period}_launch"]
        new = vt(Lx[f"{period}_version"])[:2]
        Ld = date.fromisoformat(L)
        lo, hi = (Ld - timedelta(days=365)).isoformat(), (Ld + timedelta(days=365)).isoformat()
        for proj, rs in recs.items():

            pre = [x for x in rs if lo <= x[0] < L]
            if not pre:
                continue
            last = {}
            for x in pre:
                last[x[1]] = x
            qual = preadopt = overlap = False
            for _, pkg, ver in last.values():
                lv, ak = DEC.get((pkg, ver), ({}, False))
                vs = lv.get(lib, [])
                if not vs:
                    continue
                overlap |= ak
                t = max(vt(v) for v in vs)[:2]
                if t >= new:
                    preadopt = True
                elif t[0] == new[0]:
                    qual = True
            if not qual or preadopt or overlap or owner(proj) in vend[lib]:
                continue
            first = rs[0][0]
            seq = [(p, max((vt(v) for v in DEC.get((pk, ve), ({}, 0))[0].get(lib, [])), default=())) for p, pk, ve in rs if p < L]
            seq = [(p, t) for p, t in seq if t]
            chg = None
            for (p0, t0), (p1, t1) in zip(seq, seq[1:]):
                if t1 != t0:
                    chg = p1
            since = days(chg or seq[0][0], L) if seq else 0
            post = [x for x in rs if L < x[0] <= hi]
            adopt = None
            for p, pk, ve in post:
                vs = [v for v in DEC.get((pk, ve), ({}, 0))[0].get(lib, []) if STABLE.fullmatch(v) and vt(v)[:2] >= new]
                if vs and adopt is None:
                    adopt = days(L, p)
            extra = {}
            for h in (240, 365):
                xs = [(p, pk, ve) for p, pk, ve in post if days(L, p) <= h]
                olds = [any(vt(v)[:2] < new for v in DEC.get((pk, ve), ({}, 0))[0].get(lib, [])) for p, pk, ve in xs]
                extra[f"old{h}"] = int(any(olds)) if xs else ""
            a240 = int(adopt is not None and adopt <= 240)
            act240 = int(any(days(L, x[0]) <= 240 for x in post))
            rows.append(dict(cohort=f"{lib}|{period}", library=lib, group="cmp", period=period, project=proj,
                             owner=owner(proj), releases_pre=len(pre), artifacts_pre=len(last),
                             any_213=int(any(x[1].endswith("_2.13") for x in pre)),
                             age_years=round(days(first, L) / 365.25, 3), days_since_change=since, clpe=0, http=0,
                             act240=act240, act365=int(bool(post)), adopt_days=adopt if adopt is not None else "",
                             y1=a240 if act240 else "", y1u=a240, **extra))

# ---- rule 4: qualification and selection (no adoption share is computed here) ----
size = defaultdict(lambda: defaultdict(lambda: [0, 0]))
for r in rows:
    size[r["library"]][r["period"]][0] += 1
    size[r["library"]][r["period"]][1] += r["act240"]
table = {lib: {p: dict(risk_set=size[lib][p][0], active240=size[lib][p][1]) for p in ("early", "late")} for lib in LIBS}
qual = [lib for lib in LIBS if all(table[lib][p]["active240"] >= 30 for p in ("early", "late"))]
qual.sort(key=lambda lib: -table[lib]["early"]["risk_set"])
keep = qual[:5]
rank = {lib: i for i, lib in enumerate(keep)}
best = {}
for r in rows:
    if r["library"] in rank:
        k = (r["period"], r["project"])
        if k not in best or rank[r["library"]] < rank[best[k]]:
            best[k] = r["library"]
for r in rows:
    r["kept"] = int(r["library"] in rank)
    r["pooled"] = int(r["library"] in rank and best[(r["period"], r["project"])] == r["library"])
with open(O / "bench_cohorts.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
out = dict(sizes=table, vendor_owners={k: sorted(v) for k, v in vend.items()}, qualifying=qual, kept=keep,
           pooled_counts={p: sum(1 for r in rows if r["pooled"] and r["period"] == p) for p in ("early", "late")})
(O / "r4_benchmarks.json").write_text(json.dumps(out, indent=1))
print(json.dumps({k: v for k, v in out.items() if k != "vendor_owners"}, indent=1))
print("vendor owners:", out["vendor_owners"])
