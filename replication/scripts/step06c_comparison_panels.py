"""Step 6c: comparison risk set, quarterly supplier-update panels for Akka and comparison groups,
pre-event trend tests and common-support diagnostics. Rule: outputs/step06/comparison_rule.md.

Akka group  : non-vendor projects in outputs/step05/risk_set_v2.csv (Step 4 release data).
Comparison  : projects whose latest pre-event release of some artifact declares cats-effect, fs2,
              http4s or ZIO (non-test, non-optional) and no Akka; projects in the Akka risk set excluded.
Tracked line: Akka core (2.x versions of com.typesafe.akka, non-HTTP) else Akka HTTP; comparison
              priority cats-effect > ZIO > fs2 > http4s, fixed from the last pre-event releases.
Measures per project-quarter with >=1 release declaring the tracked line (M1 upgrade, M2 freshness,
M3 latest line); see the rule file. Akka 2.9+ (not on Maven Central, no dates) count as fresh and latest.
Outputs: outputs/step06/cmp_risk_set.csv, panel_quarters.csv, pretrend_tests.json, balance.csv, counts.json
Run with the project venv (statsmodels).
"""
import csv
import json
import re
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

ROOT = Path(__file__).resolve().parents[1]
R4, R6, O = ROOT / "data/raw/step04", ROOT / "data/raw/step06", ROOT / "outputs/step06"
O.mkdir(parents=True, exist_ok=True)
EVENT, PEKKO1, HORIZON, PRE_FROM = "2022-09-07", "2023-07-10", "2025-09-30", "2020-09-07"
ALIAS = {"github.com/eclipse/ditto": "github.com/eclipse-ditto/ditto",
         "github.com/balmungsan/neotypes": "github.com/neotypes/neotypes"}
PRIORITY = ["cats_effect", "zio", "fs2", "http4s"]
PRE_Q = ["2020Q4", "2021Q1", "2021Q2", "2021Q3", "2021Q4", "2022Q1", "2022Q2"]


def norm_repo(u, pkg):
    if u:
        m = re.search(r"github\.com[:/]+([^/\s]+)/([^/\s#?]+)", u)
        if m:
            r = ("github.com/" + m.group(1) + "/" + re.sub(r"\.git$", "", m.group(2))).lower()
            return ALIAS.get(r, r)
    return "maven:" + pkg.split(":")[0].lower()


def vt(v):
    return tuple(int(x) for x in re.findall(r"\d+", v.split("-")[0])[:3]) if v else ()


def line_of(name, ver):
    g, a = name.split(":", 1)
    if g == "com.typesafe.akka" or g.startswith("com.lightbend.akka"):
        if a.startswith("akka-http"):
            return "akka_http"
        if g == "com.typesafe.akka" and ver.startswith("2."):
            return "akka"
        return "akka_other"
    if g == "org.apache.pekko":
        return "pekko"
    if a.startswith("cats-effect"):
        return "cats_effect"
    if g == "co.fs2":
        return "fs2"
    if g == "org.http4s":
        return "http4s"
    if g == "dev.zio":
        return "zio"
    return None


# ---------- supplier versions: dates and stable minor lines ----------
sup = defaultdict(dict)
for r in csv.DictReader(open(R6 / "supplier_versions.csv", encoding="utf-8")):
    sup[r["line"]][r["version"]] = r["published"]
minors = defaultdict(list)
for line, vs in sup.items():
    first = {}
    for v, d in vs.items():
        if re.fullmatch(r"\d+\.\d+\.\d+", v):
            k = vt(v)[:2]
            first[k] = min(first.get(k, d), d)
    minors[line] = sorted((k[0], k[1], d) for k, d in first.items())


def fresh_and_latest(line, ver, rel_date):
    t = vt(ver)
    if len(t) < 2:
        return None, None
    if line == "akka" and t[:2] >= (2, 9):  # not on Central: BSL, newest lines
        return 1, 1
    pub = sup[line].get(ver)
    fresh = int(pub is not None and pub >= (date.fromisoformat(rel_date) - timedelta(days=365)).isoformat())
    cutoff = (date.fromisoformat(rel_date) - timedelta(days=90)).isoformat()
    same_major = [(mj, mn) for mj, mn, d in minors[line] if mj == t[0] and d <= cutoff]
    latest = int(bool(same_major) and t[:2] >= max(same_major))
    return fresh, latest


# ---------- release-level records ----------
recs = []
v2 = {r["project"]: r for r in csv.DictReader(open(ROOT / "outputs/step05/risk_set_v2.csv", encoding="utf-8"))}
p2proj = {}
for p in csv.DictReader(open(ROOT / "outputs/step04/project_panel.csv", encoding="utf-8")):
    p2proj[(p["package"], p["version"])] = (p["project"], p["published"])
akka_lines = defaultdict(dict)
for d in csv.DictReader(open(R4 / "release_deps.csv", encoding="utf-8")):
    if d["scope"] == "test" or d["optional"] == "true" or not d["dep_version"]:
        continue
    ln = line_of(d["dep_group"] + ":" + d["dep_artifact"], d["dep_version"])
    if ln:
        cur = akka_lines[(d["package"], d["version"])].get(ln, "")
        if vt(d["dep_version"]) > vt(cur):
            akka_lines[(d["package"], d["version"])][ln] = d["dep_version"]
for (pkg, ver), (proj, pub) in p2proj.items():
    if proj in v2:
        recs.append(dict(group="akka", project=proj, package=pkg, version=ver, published=pub,
                         lines=akka_lines.get((pkg, ver), {})))

vers = {}
latest_repo = {}
for r in csv.DictReader(open(R6 / "bq_cmp_versions.csv", encoding="utf-8")):
    vers[(r["package"], r["version"])] = r
    if r["source_repo"] and (r["published"] or "") >= latest_repo.get(r["package"], ("", ""))[0]:
        latest_repo[r["package"]] = (r["published"] or "", r["source_repo"])
cmp_lines = {}
for l in open(R6 / "bq_cmp_declared.jsonl", encoding="utf-8"):
    j = json.loads(l)
    ls = {}
    for x in j["deps"]:
        v = x.get("Version") or ""
        if (x.get("Scope") or "").lower() == "test" or str(x.get("Optional")).lower() == "true" or not v or "${" in v:
            continue
        ln = line_of(x["Name"], v)
        if ln and vt(v) > vt(ls.get(ln, "")):
            ls[ln] = v
    cmp_lines[(j["package"], j["version"])] = ls
n_overlap_akka_riskset = 0
for (pkg, ver), r in vers.items():
    pub = (r["published"] or "")[:10]
    if not pub:
        continue
    proj = norm_repo(latest_repo.get(pkg, ("", ""))[1], pkg)
    if proj in v2:
        n_overlap_akka_riskset += 1
        continue
    recs.append(dict(group="cmp", project=proj, package=pkg, version=ver, published=pub,
                     lines=cmp_lines.get((pkg, ver), {})))

# ---------- risk sets and tracked line ----------
by_proj = defaultdict(list)
for r in recs:
    by_proj[(r["group"], r["project"])].append(r)
proj_rows = []
dropped_both = 0
for (g, proj), rs in by_proj.items():
    rs.sort(key=lambda x: x["published"])
    pre = [x for x in rs if PRE_FROM <= x["published"] < EVENT]
    if not pre:
        continue
    last_pre = {}
    for x in pre:
        last_pre[x["package"]] = x
    lp_lines = set().union(*[set(x["lines"]) for x in last_pre.values()])
    if g == "cmp":
        if not lp_lines & set(PRIORITY):
            continue
        if lp_lines & {"akka", "akka_http", "akka_other"}:
            dropped_both += 1
            continue
        tracked = next(l for l in PRIORITY if l in lp_lines)
    else:
        if v2[proj]["vendor"] == "1":
            continue
        tracked = "akka" if "akka" in lp_lines else ("akka_http" if "akka_http" in lp_lines else "")
    post = [x for x in rs if EVENT <= x["published"] <= HORIZON]
    proj_rows.append(dict(group=g, project=proj, tracked=tracked, n_artifacts=len(last_pre),
                          rel_per_year_pre=round(len(pre) / 2.0, 2),
                          scala3_pre=int(any(x["package"].endswith("_3") for x in pre)),
                          age_years_at_event=round((date.fromisoformat(EVENT) - date.fromisoformat(
                              min(x["published"] for x in rs if x["published"] >= "2005-01-01"))).days / 365.25, 2),
                          active_post=int(bool(post)),
                          owner=proj.split("/")[1] if proj.startswith("github.com/") else proj))
pr = pd.DataFrame(proj_rows)
pr.to_csv(O / "cmp_risk_set.csv", index=False)
keep = {(r["group"], r["project"]): r["tracked"] for r in proj_rows if r["tracked"]}


def quarter(d):
    return f"{d[:4]}Q{(int(d[5:7]) - 1) // 3 + 1}"


rows = []
for (g, proj), tracked in keep.items():
    rs = sorted(by_proj[(g, proj)], key=lambda x: x["published"])
    prev = {}
    q_recs = defaultdict(list)
    for x in rs:
        v = x["lines"].get(tracked, "")
        up = int(bool(v) and x["package"] in prev and vt(v) > vt(prev[x["package"]]))
        if v:
            prev[x["package"]] = v
        if "2020-10-01" <= x["published"] <= HORIZON:
            q_recs[quarter(x["published"])].append((x, v, up))
    for q, xs in q_recs.items():
        with_line = [t for t in xs if t[1]]
        row = dict(group=g, project=proj, quarter=q, n_releases=len(xs), declares_line=int(bool(with_line)),
                   any_pekko=int(any("pekko" in t[0]["lines"] for t in xs)), M1=np.nan, M2=np.nan, M3=np.nan)
        if with_line:
            row["M1"] = int(any(t[2] for t in with_line))
            x, v, _ = max(with_line, key=lambda t: t[0]["published"])
            f, l = fresh_and_latest(tracked, v, x["published"])
            row["M2"] = np.nan if f is None else f
            row["M3"] = np.nan if l is None else l
        rows.append(row)
pq = pd.DataFrame(rows)
pq["owner"] = pq["project"].map(lambda p: p.split("/")[1] if p.startswith("github.com/") else p)
pq["akka"] = (pq["group"] == "akka").astype(int)
pq.to_csv(O / "panel_quarters.csv", index=False)

# ---------- pre-trend tests ----------
tests = {}
for m in ("M1", "M2", "M3"):
    d = pq[pq["quarter"].isin(PRE_Q) & pq[m].notna()].copy()
    d[m] = d[m].astype(float)
    grp = pd.factorize(d["owner"])[0]
    fit = smf.ols(f"{m} ~ C(quarter) + akka + akka:C(quarter)", data=d).fit(cov_type="cluster", cov_kwds={"groups": grp})
    names = [n for n in fit.params.index if n.startswith("akka:")]
    R = np.zeros((len(names), len(fit.params)))
    for i, n in enumerate(names):
        R[i, list(fit.params.index).index(n)] = 1
    w = fit.wald_test(R, scalar=True)
    d["t"] = d["quarter"].map({q: i for i, q in enumerate(PRE_Q)})
    fit2 = smf.ols(f"{m} ~ C(quarter) + akka + akka:t", data=d).fit(cov_type="cluster", cov_kwds={"groups": grp})
    means = d.groupby(["quarter", "group"])[m].mean().unstack().round(3)
    tests[m] = dict(n_obs=len(d), n_akka_projects=int(d[d.akka == 1].project.nunique()),
                    n_cmp_projects=int(d[d.akka == 0].project.nunique()),
                    joint_F=round(float(w.statistic), 3), joint_p=round(float(w.pvalue), 4), df=len(names),
                    linear_trend_diff=round(float(fit2.params["akka:t"]), 4),
                    linear_trend_p=round(float(fit2.pvalues["akka:t"]), 4),
                    level_diff_pre=round(float(d[d.akka == 1][m].mean() - d[d.akka == 0][m].mean()), 3),
                    quarterly_means=means.to_dict())
(O / "pretrend_tests.json").write_text(json.dumps(tests, indent=1, default=str))

# ---------- descriptive pre/post difference (not the E3 estimator; that is fixed in Step 8) ----------
s3 = {(r["group"], r["project"]): r["scala3_pre"] for r in proj_rows}
pq["scala3_pre"] = [s3[(g, p)] for g, p in zip(pq.group, pq.project)]
POST_Q = [q for q in sorted(pq.quarter.unique()) if q >= "2022Q4"]
did = {}
for m in ("M1", "M3"):
    for lab, sub in (("all", pq), ("scala3_pre=0", pq[pq.scala3_pre == 0]), ("scala3_pre=1", pq[pq.scala3_pre == 1])):
        d = sub[sub.quarter.isin(PRE_Q + POST_Q) & sub[m].notna()].copy()
        d[m] = d[m].astype(float)
        d["post"] = d.quarter.isin(POST_Q).astype(int)
        f = smf.ols(f"{m} ~ C(quarter) + akka + akka:post", data=d).fit(
            cov_type="cluster", cov_kwds={"groups": pd.factorize(d["owner"])[0]})
        did[f"{m} {lab}"] = dict(coef=round(float(f.params["akka:post"]), 3), se=round(float(f.bse["akka:post"]), 3),
                                 n_akka=int(d[d.akka == 1].project.nunique()), n_cmp=int(d[d.akka == 0].project.nunique()))
(O / "did_descriptive.json").write_text(json.dumps(did, indent=1))
print(json.dumps(did, indent=1))

# ---------- balance / common support ----------
b = pr[pr["tracked"] != ""].copy()
b["akka"] = (b["group"] == "akka").astype(int)
b["log_rel"] = np.log1p(b["rel_per_year_pre"])
b["log_art"] = np.log1p(b["n_artifacts"])
ps = smf.logit("akka ~ log_rel + log_art + scala3_pre + age_years_at_event", data=b).fit(disp=0)
b["ps"] = ps.predict(b)
n_before = len(b)
b = b[(b.ps >= 0.05) & (b.ps <= 0.95)].copy()  # common support (trimming rule, Crump et al. style)
trimmed = n_before - len(b)
b["w"] = np.where(b.akka == 1, 1.0, b.ps / (1 - b.ps))


def smd(x, t, w):
    m1 = np.average(x[t == 1], weights=w[t == 1])
    m0 = np.average(x[t == 0], weights=w[t == 0])
    s = np.sqrt((np.var(x[t == 1]) + np.var(x[t == 0])) / 2)
    return (m1 - m0) / s if s > 0 else 0.0


bal = []
for c in ["rel_per_year_pre", "n_artifacts", "scala3_pre", "age_years_at_event"]:
    x, t = b[c].astype(float).values, b["akka"].values
    bal.append(dict(covariate=c, mean_akka=round(x[t == 1].mean(), 3), mean_cmp=round(x[t == 0].mean(), 3),
                    smd_raw=round(smd(x, t, np.ones(len(x))), 3), smd_weighted=round(smd(x, t, b["w"].values), 3)))
pd.DataFrame(bal).to_csv(O / "balance.csv", index=False)
cmp_ = pr[pr.group == "cmp"]
cnt = dict(cmp_risk_set=len(cmp_), cmp_active=int(cmp_.active_post.sum()),
           cmp_by_tracked=dict(Counter(cmp_.tracked)),
           cmp_active_by_tracked=dict(Counter(cmp_[cmp_.active_post == 1].tracked)),
           cmp_owners_active=int(cmp_[cmp_.active_post == 1].owner.nunique()),
           cmp_dropped_also_akka=dropped_both, cmp_release_rows_in_akka_riskset_projects=n_overlap_akka_riskset,
           akka_nonvendor_risk=int((pr.group == "akka").sum()),
           akka_by_tracked=dict(Counter(pr[pr.group == "akka"].tracked)),
           trimmed_outside_005_095=trimmed,
           ps_range_akka=[round(b[b.akka == 1].ps.min(), 3), round(b[b.akka == 1].ps.max(), 3)],
           ps_range_cmp=[round(b[b.akka == 0].ps.min(), 3), round(b[b.akka == 0].ps.max(), 3)],
           balance=bal)
(O / "counts.json").write_text(json.dumps(cnt, indent=1, default=str))
print(json.dumps(cnt, indent=1, default=str))
print(json.dumps({m: {k: v for k, v in t.items() if k != "quarterly_means"} for m, t in tests.items()}, indent=1))
