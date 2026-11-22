"""Step 9e: Elasticsearch vs comparison libraries (SolrJ, Lucene core, HBase client): risk sets, quarterly
supplier-update panels, pre-trend tests, common support and descriptive differences. Rule:
outputs/step09/comparison_rule.md (mirrors step06c for Akka).

ES group   : non-vendor projects in outputs/step08/es_risk_set.csv (group 'direct'); tracked line = highest
             resolved version across restricted Elasticsearch artifacts (outputs/step08/es_artifact_licences.csv).
Comparison : projects whose latest pre-event release (2019-01-14..2021-01-13) of some artifact declares a
             comparison library (non-test, non-optional) and no Elasticsearch/OpenSearch artifact; projects in
             the ES risk set excluded. Tracked line priority SolrJ > Lucene > HBase.
Measures per project-quarter with >=1 release declaring the tracked line: M1 upgrade, M2 freshness, M3 latest
line; ES-only M1 split into raises staying <=7.10.2 (M1_open) and raises into >7.10.2 (M1_restr).
Strata: embedded (ES server jar without client; comparison tracked = Lucene) vs client; CodeLibs; BOM-managed
(tracked version set by an external parent, i.e. a parent whose groupId differs from the package's).
Outputs (outputs/step09/): cmp_risk_set.csv, panel_quarters.csv, pretrend_tests.json, balance.csv,
                           did_descriptive.json, reversal_window.json, counts.json
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
R8, R9, O = ROOT / "data/raw/step08", ROOT / "data/raw/step09", ROOT / "outputs/step09"
O.mkdir(parents=True, exist_ok=True)
EVENT, PRE_FROM, HORIZON, REV_END = "2021-01-14", "2019-01-14", "2024-11-11", "2025-09-30"
PRE_Q = [f"{y}Q{q}" for y in (2019, 2020) for q in (1, 2, 3, 4)]
POST_Q = [f"{y}Q{q}" for y in range(2021, 2025) for q in (1, 2, 3, 4) if f"{y}Q{q}" <= "2024Q3"]
REV_Q = ["2024Q4", "2025Q1", "2025Q2", "2025Q3"]
PRIORITY = ["solrj", "lucene", "hbase"]
CMP_LINE = {"org.apache.solr:solr-solrj": "solrj", "org.apache.lucene:lucene-core": "lucene",
            "org.apache.hbase:hbase-client": "hbase"}


def vt(v):
    return tuple(int(x) for x in re.findall(r"\d+", v.split("-")[0])[:3]) if v else ()


def quarter(d):
    return f"{d[:4]}Q{(int(d[5:7]) - 1) // 3 + 1}"


def norm_repo(u, pkg):
    if u:
        m = re.search(r"github\.com[:/]+([^/\s]+)/([^/\s#?]+)", u)
        if m:
            return ("github.com/" + m.group(1) + "/" + re.sub(r"\.git$", "", m.group(2))).lower()
    return "maven:" + pkg.split(":")[0].lower()


HOSTS = {"com.github", "io.github", "com.gitlab", "io.gitlab", "org.apache", "org.eclipse"}


def gprefix(name):
    """Organisation part of a groupId: two components, three under shared hosts (com.github.x, org.apache.x)."""
    parts = name.split(":")[0].split(".")
    return ".".join(parts[:3] if ".".join(parts[:2]) in HOSTS else parts[:2])


# ---------- supplier version dates (deps.dev API caches) ----------
def api_versions(path):
    d = json.loads(Path(path).read_text())
    return {v["versionKey"]["version"]: (v.get("publishedAt") or "")[:10] for v in d.get("versions", []) if v.get("publishedAt")}


sup = {"es": api_versions(R8 / "api/org.elasticsearch__elasticsearch.json")}
for k, v in api_versions(R8 / "api/org.elasticsearch.client__elasticsearch-rest-high-level-client.json").items():
    sup["es"][k] = min(sup["es"].get(k, v), v)
for name, line in CMP_LINE.items():
    sup[line] = api_versions(R9 / "api" / (name.replace(":", "__") + ".json"))
minors = {}
for line, vs in sup.items():
    first = {}
    for v, d in vs.items():
        if re.fullmatch(r"\d+\.\d+\.\d+", v):
            first[vt(v)[:2]] = min(first.get(vt(v)[:2], d), d)
    minors[line] = sorted((k[0], k[1], d) for k, d in first.items())


def fresh_and_latest(line, ver, rel_date):
    t = vt(ver)
    if len(t) < 2:
        return None, None
    pub = sup[line].get(ver)
    fresh = int(pub is not None and pub >= (date.fromisoformat(rel_date) - timedelta(days=365)).isoformat())
    cutoff = (date.fromisoformat(rel_date) - timedelta(days=90)).isoformat()
    same_major = [(mj, mn) for mj, mn, d in minors[line] if mj == t[0] and d <= cutoff]
    return fresh, int(bool(same_major) and t[:2] >= max(same_major))


# ---------- external management flag and package age ----------
def external_source(d):
    """Version supplied by a POM in the parent chain or an imported BOM whose groupId prefix differs from the
    package's (e.g. spring-boot-dependencies), as recorded by the resolvers in resolved_from."""
    src = d.get("resolved_from", "")
    return d["resolution"] in ("parent_dm", "parent_props") and bool(src) and gprefix(src) != gprefix(d["package"])


FIRST = {}  # first publication of any version of a package (both version tables cover all versions)
for f in (ROOT / "data/raw/step07_pooled/bq_es_versions.csv", R9 / "bq_cmp_versions.csv"):
    for r in csv.DictReader(open(f, encoding="utf-8")):
        d = (r["published"] or "")[:10]
        if d >= "2005-01-01" and d < FIRST.get(r["package"], "9999"):
            FIRST[r["package"]] = d


# ---------- ES group: release-level tracked versions ----------
lic = {r["artifact"]: r["class"] for r in csv.DictReader(open(ROOT / "outputs/step08/es_artifact_licences.csv", encoding="utf-8"))}
es_rel = defaultdict(dict)  # (pkg, ver) -> {"es": version, "bom": bool, "server": bool, "client": bool, "os": bool}
for d in csv.DictReader(open(R8 / "es_release_deps.csv", encoding="utf-8")):
    if d["scope"] == "test" or d["optional"] == "true":
        continue
    k, dep = (d["package"], d["version"]), d["dep"]
    e = es_rel[k]
    if dep.startswith("org.opensearch"):
        e["os"] = True
    if dep.startswith("org.elasticsearch") and lic.get(dep) == "restricted" and not dep.startswith("org.elasticsearch:elasticsearch-spark"):
        if dep == "org.elasticsearch:elasticsearch":
            e["server"] = True
        elif dep.startswith("org.elasticsearch.client:"):
            e["client"] = True
        if d["dep_version"] and vt(d["dep_version"]) > vt(e.get("es", "")):
            e["es"] = d["dep_version"]
            e["bom"] = external_source(d)
es_risk = {r["project"]: r for r in csv.DictReader(open(ROOT / "outputs/step08/es_risk_set.csv", encoding="utf-8"))
           if r["group"] == "direct"}
recs = []
for p in csv.DictReader(open(ROOT / "outputs/step08/es_project_panel.csv", encoding="utf-8")):
    r = es_risk.get(p["project"])
    if r is None or r["vendor"] == "1" or r["fork_affiliated"] == "1":
        continue
    e = es_rel.get((p["package"], p["version"]), {})
    recs.append(dict(group="es", project=p["project"], package=p["package"], version=p["version"], published=p["published"],
                     v=e.get("es", ""), bom=e.get("bom", False), server=e.get("server", False),
                     client=e.get("client", False), os=e.get("os", False), agpl=vt(e.get("es", "")) >= (8, 16, 0)))

# ---------- comparison group ----------
cmp_rel = defaultdict(dict)
es_overlap_rel = set()
for d in csv.DictReader(open(R9 / "cmp_release_deps.csv", encoding="utf-8")):
    if d["scope"] == "test" or d["optional"] == "true":
        continue
    k, dep = (d["package"], d["version"]), d["dep"]
    if dep.startswith(("org.elasticsearch", "co.elastic.clients", "org.opensearch")):
        es_overlap_rel.add(k)
        continue
    line = CMP_LINE.get(dep)
    if not line:
        continue
    e = cmp_rel[k].setdefault(line, {"v": "", "bom": False})
    if d["dep_version"] and vt(d["dep_version"]) > vt(e["v"]):
        e["v"] = d["dep_version"]
        e["bom"] = external_source(d)
    elif not d["dep_version"]:
        e.setdefault("present", True)
vers, latest_repo = {}, {}
for r in csv.DictReader(open(R9 / "bq_cmp_versions.csv", encoding="utf-8")):
    vers[(r["package"], r["version"])] = (r["published"] or "")[:10]
    if r["source_repo"] and (r["published"] or "") >= latest_repo.get(r["package"], ("", ""))[0]:
        latest_repo[r["package"]] = (r["published"] or "", r["source_repo"])
for (pkg, ver), pub in vers.items():
    if not pub:
        continue
    proj = norm_repo(latest_repo.get(pkg, ("", ""))[1], pkg)
    if proj in es_risk:
        continue
    recs.append(dict(group="cmp", project=proj, package=pkg, version=ver, published=pub,
                     lines=cmp_rel.get((pkg, ver), {}), es_overlap=(pkg, ver) in es_overlap_rel))

# ---------- risk sets, tracked line and project covariates ----------
by_proj = defaultdict(list)
for r in recs:
    by_proj[(r["group"], r["project"])].append(r)
proj_rows, dropped_es_overlap = [], 0
for (g, proj), rs in by_proj.items():
    rs.sort(key=lambda x: x["published"])
    pre = [x for x in rs if PRE_FROM <= x["published"] < EVENT]
    if not pre:
        continue
    last_pre = {}
    for x in pre:
        last_pre[x["package"]] = x
    if g == "cmp":
        lp = set().union(*[set(x["lines"]) for x in last_pre.values()])
        if not lp & set(PRIORITY):
            continue
        if any(x["es_overlap"] for x in last_pre.values()):
            dropped_es_overlap += 1
            continue
        tracked = next(l for l in PRIORITY if l in lp)
        for x in rs:
            t = x["lines"].get(tracked, {})
            x["v"], x["bom"] = t.get("v", ""), t.get("bom", False)
        stratum = "embedded" if tracked == "lucene" else "client"
    else:
        tracked = "es"
        server = any(x["server"] for x in last_pre.values())
        client = any(x["client"] for x in last_pre.values())
        stratum = "embedded" if server and not client else "client"
    owner = proj.split("/")[1] if proj.startswith("github.com/") else proj
    post = [x for x in rs if EVENT <= x["published"] <= HORIZON]
    dated = [x["published"] for x in rs if x["published"] >= "2005-01-01"] + [FIRST[x["package"]] for x in rs if x["package"] in FIRST]
    proj_rows.append(dict(group=g, project=proj, owner=owner, tracked=tracked, stratum=stratum,
                          codelibs=int(owner == "codelibs"), n_artifacts=len(last_pre),
                          rel_per_year_pre=round(len(pre) / 2.0, 2),
                          bom_pre=int(any(x["bom"] for x in last_pre.values() if x["v"])),
                          age_years_at_event=round((date.fromisoformat(EVENT) - date.fromisoformat(min(dated))).days / 365.25, 2),
                          active_post=int(bool(post))))
pr = pd.DataFrame(proj_rows)
pr.to_csv(O / "cmp_risk_set.csv", index=False)
info = {(r["group"], r["project"]): r for r in proj_rows}

# ---------- quarterly panel ----------
rows = []
for (g, proj), r in info.items():
    rs = sorted(by_proj[(g, proj)], key=lambda x: x["published"])
    prev, q_recs = {}, defaultdict(list)
    for x in rs:
        v = x["v"]
        prev_before = dict(prev)
        up = int(bool(v) and x["package"] in prev and vt(v) > vt(prev[x["package"]]))
        up_restr = int(up and g == "es" and vt(v) > (7, 10, 2))
        if v:
            prev[x["package"]] = v
        if "2019-01-01" <= x["published"] <= REV_END:
            q_recs[quarter(x["published"])].append((x, v, up, up_restr, int(bool(v) and x["package"] in prev_before)))
    for q, xs in q_recs.items():
        wl = [t for t in xs if t[1]]
        row = dict(group=g, project=proj, owner=r["owner"], quarter=q, stratum=r["stratum"], codelibs=r["codelibs"],
                   bom_pre=r["bom_pre"], declares_line=int(bool(wl)), M1=np.nan, M1_restr=np.nan, M1_open=np.nan,
                   M2=np.nan, M3=np.nan, M1c=np.nan,
                   any_os=int(any(t[0].get("os") for t in xs)), any_agpl=int(any(t[0].get("agpl") for t in xs)))
        if wl:
            row["M1"] = int(any(t[2] for t in wl))
            wc = [t for t in wl if t[4]]  # left-censoring fix: only releases with an earlier declared version
            row["M1c"] = int(any(t[2] for t in wc)) if wc else np.nan
            if g == "es":
                row["M1_restr"] = int(any(t[3] for t in wl))
                row["M1_open"] = int(any(t[2] and not t[3] for t in wl))
            x, v = max(wl, key=lambda t: t[0]["published"])[:2]
            f, l = fresh_and_latest(r["tracked"], v, x["published"])
            row["M2"] = np.nan if f is None else f
            row["M3"] = np.nan if l is None else l
        rows.append(row)
pq = pd.DataFrame(rows)
pq["es"] = (pq["group"] == "es").astype(int)
pq.to_csv(O / "panel_quarters.csv", index=False)


def cluster_fit(formula, d):
    return smf.ols(formula, data=d).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(d["owner"])[0]})


# ---------- pre-trend tests ----------
tests = {}
for lab, sub in (("all", pq), ("excl_codelibs", pq[pq.codelibs == 0]), ("client", pq[pq.stratum == "client"]),
                 ("embedded", pq[pq.stratum == "embedded"])):
    for m in ("M1", "M1c", "M2", "M3"):
        d = sub[sub.quarter.isin(PRE_Q) & sub[m].notna()].copy()
        d[m] = d[m].astype(float)
        fit = cluster_fit(f"{m} ~ C(quarter) + es + es:C(quarter)", d)
        names = [n for n in fit.params.index if n.startswith("es:")]
        R = np.zeros((len(names), len(fit.params)))
        for i, n in enumerate(names):
            R[i, list(fit.params.index).index(n)] = 1
        w = fit.wald_test(R, scalar=True)
        d["t"] = d.quarter.map({q: i for i, q in enumerate(PRE_Q)})
        fit2 = cluster_fit(f"{m} ~ C(quarter) + es + es:t", d)
        tests[f"{m} {lab}"] = dict(
            n_obs=len(d), n_es=int(d[d.es == 1].project.nunique()), n_cmp=int(d[d.es == 0].project.nunique()),
            joint_F=round(float(w.statistic), 3), joint_p=round(float(w.pvalue), 4), df=len(names),
            linear_trend_diff=round(float(fit2.params["es:t"]), 4), linear_trend_p=round(float(fit2.pvalues["es:t"]), 4),
            level_diff_pre=round(float(d[d.es == 1][m].mean() - d[d.es == 0][m].mean()), 3),
            quarterly_means=d.groupby(["quarter", "group"])[m].mean().unstack().round(3).to_dict())
(O / "pretrend_tests.json").write_text(json.dumps(tests, indent=1, default=str))

# ---------- balance / common support ----------
b = pr.copy()
b["es"] = (b.group == "es").astype(int)
b["log_rel"], b["log_art"] = np.log1p(b.rel_per_year_pre), np.log1p(b.n_artifacts)
ps = smf.logit("es ~ log_rel + log_art + age_years_at_event + bom_pre", data=b).fit(disp=0)
b["ps"] = ps.predict(b)
n_before = len(b)
b = b[(b.ps >= 0.05) & (b.ps <= 0.95)].copy()
trimmed = n_before - len(b)
b["w"] = np.where(b.es == 1, 1.0, b.ps / (1 - b.ps))


def smd(x, t, w):
    m1, m0 = np.average(x[t == 1], weights=w[t == 1]), np.average(x[t == 0], weights=w[t == 0])
    s = np.sqrt((np.var(x[t == 1]) + np.var(x[t == 0])) / 2)
    return (m1 - m0) / s if s > 0 else 0.0


bal = []
for c in ["rel_per_year_pre", "n_artifacts", "age_years_at_event", "bom_pre"]:
    x, t = b[c].astype(float).values, b.es.values
    bal.append(dict(covariate=c, mean_es=round(x[t == 1].mean(), 3), mean_cmp=round(x[t == 0].mean(), 3),
                    smd_raw=round(smd(x, t, np.ones(len(x))), 3), smd_weighted=round(smd(x, t, b.w.values), 3)))
pd.DataFrame(bal).to_csv(O / "balance.csv", index=False)
wmap = {(g, p): w for g, p, w in zip(b.group, b.project, b.w)}

# ---------- descriptive pre/post differences (not the confirmatory estimator; that is fixed in Step 10) ----------
did = {}
pq["w"] = [wmap.get((g, p), np.nan) for g, p in zip(pq.group, pq.project)]
for m in ("M1", "M1c", "M3"):
    for lab, sub in (("all", pq), ("excl_codelibs", pq[pq.codelibs == 0]), ("client", pq[pq.stratum == "client"]),
                     ("embedded", pq[pq.stratum == "embedded"]), ("bom_pre=1", pq[pq.bom_pre == 1]),
                     ("bom_pre=0", pq[pq.bom_pre == 0])):
        d = sub[sub.quarter.isin(PRE_Q + POST_Q) & sub[m].notna()].copy()
        d[m] = d[m].astype(float)
        d["post"] = d.quarter.isin(POST_Q).astype(int)
        f = cluster_fit(f"{m} ~ C(quarter) + es + es:post", d)
        res = dict(coef=round(float(f.params["es:post"]), 3), se=round(float(f.bse["es:post"]), 3),
                   n_es=int(d[d.es == 1].project.nunique()), n_cmp=int(d[d.es == 0].project.nunique()),
                   n_owner_clusters=int(d.owner.nunique()))
        dw = d[d.w.notna()]
        if dw.es.nunique() == 2:
            fw = smf.wls(f"{m} ~ C(quarter) + es + es:post", data=dw, weights=dw.w).fit(
                cov_type="cluster", cov_kwds={"groups": pd.factorize(dw["owner"])[0]})
            res.update(coef_weighted=round(float(fw.params["es:post"]), 3), se_weighted=round(float(fw.bse["es:post"]), 3))
        did[f"{m} {lab}"] = res
es_m1 = pq[(pq.es == 1) & pq.M1.notna()]
did["es_M1_decomposition"] = {
    per: dict(n_project_quarters=int(len(d)), M1=round(float(d.M1.mean()), 3), M1_open=round(float(d.M1_open.mean()), 3),
              M1_restr=round(float(d.M1_restr.mean()), 3))
    for per, d in (("pre", es_m1[es_m1.quarter.isin(PRE_Q)]), ("post", es_m1[es_m1.quarter.isin(POST_Q)]))}
did["cmp_M1"] = {per: round(float(pq[(pq.es == 0) & pq.quarter.isin(qs)].M1.mean()), 3)
                 for per, qs in (("pre", PRE_Q), ("post", POST_Q))}
(O / "did_descriptive.json").write_text(json.dumps(did, indent=1))

# ---------- reversal window (descriptive) ----------
es_q = pq[(pq.es == 1) & pq.quarter.isin(["2023Q4", "2024Q1", "2024Q2", "2024Q3"] + REV_Q)]
rev = dict(es_quarterly=es_q.groupby("quarter")[["any_agpl", "any_os", "M1", "M1_restr"]].mean().round(3).to_dict(),
           es_project_quarters=es_q.groupby("quarter").size().to_dict(),
           cmp_M1=pq[(pq.es == 0) & pq.quarter.isin(["2024Q1", "2024Q2", "2024Q3"] + REV_Q)].groupby("quarter").M1.mean().round(3).to_dict())
(O / "reversal_window.json").write_text(json.dumps(rev, indent=1, default=str))

# ---------- counts ----------
c_ = pr[pr.group == "cmp"]
pre_dependents = {l: int((c_.tracked == l).sum()) for l in PRIORITY}
cnt = dict(cmp_risk_set=len(c_), cmp_active=int(c_.active_post.sum()), cmp_by_tracked=pre_dependents,
           cmp_active_by_tracked=dict(Counter(c_[c_.active_post == 1].tracked)),
           cmp_owners_active=int(c_[c_.active_post == 1].owner.nunique()),
           rule5_common_support_pass={l: n >= 50 for l, n in pre_dependents.items()},
           cmp_dropped_es_overlap=dropped_es_overlap,
           es_risk=int((pr.group == "es").sum()), es_active=int(pr[pr.group == "es"].active_post.sum()),
           es_by_stratum=dict(Counter(pr[pr.group == "es"].stratum)),
           cmp_by_stratum=dict(Counter(c_.stratum)),
           bom_pre_share=dict(es=round(pr[pr.group == "es"].bom_pre.mean(), 3), cmp=round(c_.bom_pre.mean(), 3)),
           trimmed_outside_005_095=trimmed,
           ps_range=dict(es=[round(b[b.es == 1].ps.min(), 3), round(b[b.es == 1].ps.max(), 3)],
                         cmp=[round(b[b.es == 0].ps.min(), 3), round(b[b.es == 0].ps.max(), 3)]),
           balance=bal)
(O / "counts.json").write_text(json.dumps(cnt, indent=1, default=str))
print(json.dumps(cnt, indent=1, default=str))
print(json.dumps({k: {kk: vv for kk, vv in t.items() if kk != "quarterly_means"} for k, t in tests.items()}, indent=1))
print(json.dumps(did, indent=1))
print(json.dumps(rev, indent=1, default=str))
