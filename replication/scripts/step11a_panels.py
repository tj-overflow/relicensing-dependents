"""Step 11a: project-quarter panels for both events.

Release-level construction is copied from step06c (Akka) and step09e (Elasticsearch) without change to the
risk-set, tracked-line or M1/M3 rules. Added here:
  M1c   M1 over releases with an earlier declared version of the same artifact (left-censoring fix)
  M1s   M1 over releases "at risk": the supplier line had a stable x.y.z version above the artifact's previous
        declared version, published >= 30 days before the release (calendar adjustment; robustness only)
  decomposition  Akka: M1_open = raise to <=2.6.21 (core) / <=10.2.10 (HTTP); M1_restr = raise to >=2.7.0 / >=10.4.0
                 Elasticsearch: M1_open = raise staying <=7.10.2; M1_restr = raise into >7.10.2
  period         pre / event / post / other per event
  project flags  strata, non-switcher status
Outputs: outputs/step11/panel.csv, outputs/step11/projects.csv
"""
import csv
import json
import re
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
R4, R6, R8, R9 = (ROOT / f"data/raw/step0{i}" for i in (4, 6, 8, 9))
O = ROOT / "outputs/step11"
O.mkdir(parents=True, exist_ok=True)

EV = {
    "akka": dict(event="2022-09-07", pre_from="2020-09-07", horizon="2025-09-30", panel_from="2020-10-01",
                 pre_q=[f"{y}Q{q}" for y, q in [(2020, 4)] + [(2021, k) for k in (1, 2, 3, 4)] + [(2022, 1), (2022, 2)]],
                 event_q="2022Q3", post_last="2025Q3"),
    "es": dict(event="2021-01-14", pre_from="2019-01-14", horizon="2024-11-11", panel_from="2019-01-01",
               pre_q=[f"{y}Q{q}" for y in (2019, 2020) for q in (1, 2, 3, 4)], event_q="2021Q1", post_last="2024Q3"),
}


def vt(v):
    return tuple(int(x) for x in re.findall(r"\d+", v.split("-")[0])[:3]) if v else ()


def quarter(d):
    return f"{d[:4]}Q{(int(d[5:7]) - 1) // 3 + 1}"


def period(ev, q):
    e = EV[ev]
    if q in e["pre_q"]:
        return "pre"
    if q == e["event_q"]:
        return "event"
    if e["event_q"] < q <= e["post_last"]:
        return "post"
    return "other"


def owner_of(p):
    return p.split("/")[1] if p.startswith("github.com/") else p


def stable_index(vs):
    """line versions -> sorted list of (version tuple, date) for stable x.y.z versions"""
    return sorted((vt(v), d) for v, d in vs.items() if re.fullmatch(r"\d+\.\d+\.\d+", v) and d)


def at_risk(index, prev_v, rel_date):
    """a stable supplier version above prev_v existed >= 30 days before the release"""
    if not prev_v:
        return 0
    cut = (date.fromisoformat(rel_date) - timedelta(days=30)).isoformat()
    p = vt(prev_v)
    return int(any(t > p and d <= cut for t, d in index))


def latest_flags(sup, minors, line, ver, rel_date, akka_29=False):
    t = vt(ver)
    if len(t) < 2:
        return None
    if akka_29 and t[:2] >= (2, 9):
        return 1
    cutoff = (date.fromisoformat(rel_date) - timedelta(days=90)).isoformat()
    same_major = [(mj, mn) for mj, mn, d in minors[line] if mj == t[0] and d <= cutoff]
    return int(bool(same_major) and t[:2] >= max(same_major))


def minors_of(sup):
    out = {}
    for line, vs in sup.items():
        first = {}
        for v, d in vs.items():
            if re.fullmatch(r"\d+\.\d+\.\d+", v):
                first[vt(v)[:2]] = min(first.get(vt(v)[:2], d), d)
        out[line] = sorted((k[0], k[1], d) for k, d in first.items())
    return out


def build_quarters(ev, g, proj, rs, tracked, sup_idx, minors, sup, split, extra):
    """rs: release records with x['v'] = tracked-line version; returns project-quarter rows"""
    prev, q_recs = {}, defaultdict(list)
    for x in sorted(rs, key=lambda x: x["published"]):
        v = x["v"]
        pv = prev.get(x["package"], "")
        up = int(bool(v) and bool(pv) and vt(v) > vt(pv))
        restr = int(up and split is not None and split(v))
        risk = at_risk(sup_idx, pv, x["published"]) if v else 0
        if v:
            prev[x["package"]] = v
        if EV[ev]["panel_from"] <= x["published"] <= "2025-09-30":
            q_recs[quarter(x["published"])].append(dict(x=x, v=v, up=up, restr=restr, has_prev=int(bool(pv)), risk=risk))
    rows = []
    for q, xs in q_recs.items():
        wl = [t for t in xs if t["v"]]
        row = dict(event=ev, group=g, treated=int(g != "cmp"), project=proj, owner=owner_of(proj), quarter=q,
                   period=period(ev, q), tracked=tracked, n_releases=len(xs), declares_line=int(bool(wl)),
                   M1=np.nan, M1c=np.nan, M1s=np.nan, M3=np.nan, M1_open=np.nan, M1_restr=np.nan)
        row.update(extra(xs))
        if wl:
            row["M1"] = int(any(t["up"] for t in wl))
            wc = [t for t in wl if t["has_prev"]]
            row["M1c"] = int(any(t["up"] for t in wc)) if wc else np.nan
            ws = [t for t in wl if t["risk"]]
            row["M1s"] = int(any(t["up"] for t in ws)) if ws else np.nan
            if g != "cmp":
                row["M1_restr"] = int(any(t["restr"] for t in wl))
                row["M1_open"] = int(any(t["up"] and not t["restr"] for t in wl))
            last = max(wl, key=lambda t: t["x"]["published"])
            m3 = latest_flags(sup, minors, tracked, last["v"], last["x"]["published"], akka_29=(tracked == "akka"))
            row["M3"] = np.nan if m3 is None else m3
        rows.append(row)
    return rows


# =====================================================================================================
# Akka (construction from step06c)
# =====================================================================================================
ALIAS = {"github.com/eclipse/ditto": "github.com/eclipse-ditto/ditto",
         "github.com/balmungsan/neotypes": "github.com/neotypes/neotypes"}
A_PRIORITY = ["cats_effect", "zio", "fs2", "http4s"]


def a_norm_repo(u, pkg):
    if u:
        m = re.search(r"github\.com[:/]+([^/\s]+)/([^/\s#?]+)", u)
        if m:
            r = ("github.com/" + m.group(1) + "/" + re.sub(r"\.git$", "", m.group(2))).lower()
            return ALIAS.get(r, r)
    return "maven:" + pkg.split(":")[0].lower()


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


def build_akka():
    e = EV["akka"]
    sup = defaultdict(dict)
    for r in csv.DictReader(open(R6 / "supplier_versions.csv", encoding="utf-8")):
        sup[r["line"]][r["version"]] = r["published"]
    minors = minors_of(sup)
    idx = {l: stable_index(vs) for l, vs in sup.items()}
    v2 = {r["project"]: r for r in csv.DictReader(open(ROOT / "outputs/step05/risk_set_v2.csv", encoding="utf-8"))}
    recs = []
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
    vers, latest_repo = {}, {}
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
    for (pkg, ver), r in vers.items():
        pub = (r["published"] or "")[:10]
        if not pub:
            continue
        proj = a_norm_repo(latest_repo.get(pkg, ("", ""))[1], pkg)
        if proj in v2:
            continue
        recs.append(dict(group="cmp", project=proj, package=pkg, version=ver, published=pub,
                         lines=cmp_lines.get((pkg, ver), {})))
    by_proj = defaultdict(list)
    for r in recs:
        by_proj[(r["group"], r["project"])].append(r)
    projects, rows = [], []
    for (g, proj), rs in by_proj.items():
        rs.sort(key=lambda x: x["published"])
        pre = [x for x in rs if e["pre_from"] <= x["published"] < e["event"]]
        if not pre:
            continue
        last_pre = {}
        for x in pre:
            last_pre[x["package"]] = x
        lp = set().union(*[set(x["lines"]) for x in last_pre.values()])
        if g == "cmp":
            if not lp & set(A_PRIORITY) or lp & {"akka", "akka_http", "akka_other"}:
                continue
            tracked = next(l for l in A_PRIORITY if l in lp)
        else:
            if v2[proj]["vendor"] == "1":
                continue
            tracked = "akka" if "akka" in lp else ("akka_http" if "akka_http" in lp else "")
            if not tracked:
                continue
        post = [x for x in rs if e["event"] <= x["published"] <= e["horizon"]]
        f = v2.get(proj, {})
        projects.append(dict(
            event="akka", group=g, treated=int(g == "akka"), project=proj, owner=owner_of(proj), tracked=tracked,
            n_artifacts=len(last_pre), rel_per_year_pre=round(len(pre) / 2.0, 2),
            scala3_pre=int(any(x["package"].endswith("_3") for x in pre)),
            age_years_at_event=round((date.fromisoformat(e["event"]) - date.fromisoformat(
                min(x["published"] for x in rs if x["published"] >= "2005-01-01"))).days / 365.25, 2),
            active_post=int(bool(post)),
            # strata; comparison projects carry no Akka flags
            scala3_pre_event=int(f.get("scala3_pre_event", "0") == "1"), play_user_pre=int(f.get("play_user_pre", "0") == "1"),
            http_user=int("http" in f.get("akka_modules_pre", "").split(";")),
            provided_only=int(f.get("akka_provided_or_testkit_only", "0") == "1"), foundation=f.get("foundation", ""),
            outcome=f.get("outcome_v2", ""),
            switcher=int(g == "akka" and (f.get("ever_switched") == "1" or f.get("outcome_v2") == "removed"))))
        for x in rs:
            x["v"] = x["lines"].get(tracked, "")
        split = (lambda v: vt(v) >= (2, 7, 0)) if tracked == "akka" else ((lambda v: vt(v) >= (10, 4, 0)) if tracked == "akka_http" else None)
        rows += build_quarters("akka", g, proj, rs, tracked, idx.get(tracked, []), minors, sup, split,
                               lambda xs: dict(any_fork=int(any("pekko" in t["x"]["lines"] for t in xs))))
    return projects, rows


# =====================================================================================================
# Elasticsearch (construction from step09e)
# =====================================================================================================
CMP_LINE = {"org.apache.solr:solr-solrj": "solrj", "org.apache.lucene:lucene-core": "lucene",
            "org.apache.hbase:hbase-client": "hbase"}
E_PRIORITY = ["solrj", "lucene", "hbase"]
HOSTS = {"com.github", "io.github", "com.gitlab", "io.gitlab", "org.apache", "org.eclipse"}


def gprefix(name):
    parts = name.split(":")[0].split(".")
    return ".".join(parts[:3] if ".".join(parts[:2]) in HOSTS else parts[:2])


def e_norm_repo(u, pkg):
    if u:
        m = re.search(r"github\.com[:/]+([^/\s]+)/([^/\s#?]+)", u)
        if m:
            return ("github.com/" + m.group(1) + "/" + re.sub(r"\.git$", "", m.group(2))).lower()
    return "maven:" + pkg.split(":")[0].lower()


def api_versions(path):
    d = json.loads(Path(path).read_text())
    return {v["versionKey"]["version"]: (v.get("publishedAt") or "")[:10] for v in d.get("versions", []) if v.get("publishedAt")}


def external_source(d):
    src = d.get("resolved_from", "")
    return d["resolution"] in ("parent_dm", "parent_props") and bool(src) and gprefix(src) != gprefix(d["package"])


def build_es():
    e = EV["es"]
    sup = {"es": api_versions(R8 / "api/org.elasticsearch__elasticsearch.json")}
    for k, v in api_versions(R8 / "api/org.elasticsearch.client__elasticsearch-rest-high-level-client.json").items():
        sup["es"][k] = min(sup["es"].get(k, v), v)
    for name, line in CMP_LINE.items():
        sup[line] = api_versions(R9 / "api" / (name.replace(":", "__") + ".json"))
    minors = minors_of(sup)
    idx = {l: stable_index(vs) for l, vs in sup.items()}
    first = {}
    for f in (ROOT / "data/raw/step07_pooled/bq_es_versions.csv", R9 / "bq_cmp_versions.csv"):
        for r in csv.DictReader(open(f, encoding="utf-8")):
            d = (r["published"] or "")[:10]
            if d >= "2005-01-01" and d < first.get(r["package"], "9999"):
                first[r["package"]] = d
    lic = {r["artifact"]: r["class"] for r in csv.DictReader(open(ROOT / "outputs/step08/es_artifact_licences.csv", encoding="utf-8"))}
    es_rel = defaultdict(dict)
    for d in csv.DictReader(open(R8 / "es_release_deps.csv", encoding="utf-8")):
        if d["scope"] == "test" or d["optional"] == "true":
            continue
        k, dep = (d["package"], d["version"]), d["dep"]
        x = es_rel[k]
        if dep.startswith("org.opensearch"):
            x["os"] = True
        if dep.startswith("org.elasticsearch") and lic.get(dep) == "restricted" and not dep.startswith("org.elasticsearch:elasticsearch-spark"):
            if dep == "org.elasticsearch:elasticsearch":
                x["server"] = True
            elif dep.startswith("org.elasticsearch.client:"):
                x["client"] = True
            if d["dep_version"] and vt(d["dep_version"]) > vt(x.get("es", "")):
                x["es"] = d["dep_version"]
                x["bom"] = external_source(d)
    es_risk = {r["project"]: r for r in csv.DictReader(open(ROOT / "outputs/step08/es_risk_set.csv", encoding="utf-8"))
               if r["group"] == "direct"}
    recs = []
    for p in csv.DictReader(open(ROOT / "outputs/step08/es_project_panel.csv", encoding="utf-8")):
        r = es_risk.get(p["project"])
        if r is None or r["vendor"] == "1" or r["fork_affiliated"] == "1":
            continue
        x = es_rel.get((p["package"], p["version"]), {})
        recs.append(dict(group="es", project=p["project"], package=p["package"], version=p["version"], published=p["published"],
                         v=x.get("es", ""), bom=x.get("bom", False), server=x.get("server", False),
                         client=x.get("client", False), os=x.get("os", False), agpl=vt(x.get("es", "")) >= (8, 16, 0)))
    cmp_rel, es_overlap_rel = defaultdict(dict), set()
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
        x = cmp_rel[k].setdefault(line, {"v": "", "bom": False})
        if d["dep_version"] and vt(d["dep_version"]) > vt(x["v"]):
            x["v"] = d["dep_version"]
            x["bom"] = external_source(d)
    vers, latest_repo = {}, {}
    for r in csv.DictReader(open(R9 / "bq_cmp_versions.csv", encoding="utf-8")):
        vers[(r["package"], r["version"])] = (r["published"] or "")[:10]
        if r["source_repo"] and (r["published"] or "") >= latest_repo.get(r["package"], ("", ""))[0]:
            latest_repo[r["package"]] = (r["published"] or "", r["source_repo"])
    for (pkg, ver), pub in vers.items():
        if not pub:
            continue
        proj = e_norm_repo(latest_repo.get(pkg, ("", ""))[1], pkg)
        if proj in es_risk:
            continue
        recs.append(dict(group="cmp", project=proj, package=pkg, version=ver, published=pub,
                         lines=cmp_rel.get((pkg, ver), {}), es_overlap=(pkg, ver) in es_overlap_rel))
    by_proj = defaultdict(list)
    for r in recs:
        by_proj[(r["group"], r["project"])].append(r)
    projects, rows = [], []
    for (g, proj), rs in by_proj.items():
        rs.sort(key=lambda x: x["published"])
        pre = [x for x in rs if e["pre_from"] <= x["published"] < e["event"]]
        if not pre:
            continue
        last_pre = {}
        for x in pre:
            last_pre[x["package"]] = x
        if g == "cmp":
            lp = set().union(*[set(x["lines"]) for x in last_pre.values()])
            if not lp & set(E_PRIORITY) or any(x["es_overlap"] for x in last_pre.values()):
                continue
            tracked = next(l for l in E_PRIORITY if l in lp)
            for x in rs:
                t = x["lines"].get(tracked, {})
                x["v"], x["bom"] = t.get("v", ""), t.get("bom", False)
            stratum = "embedded" if tracked == "lucene" else "client"
        else:
            tracked = "es"
            server = any(x["server"] for x in last_pre.values())
            client = any(x["client"] for x in last_pre.values())
            stratum = "embedded" if server and not client else "client"
        owner = owner_of(proj)
        post = [x for x in rs if e["event"] <= x["published"] <= e["horizon"]]
        dated = [x["published"] for x in rs if x["published"] >= "2005-01-01"] + [first[x["package"]] for x in rs if x["package"] in first]
        r8 = es_risk.get(proj, {})
        projects.append(dict(
            event="es", group=g, treated=int(g == "es"), project=proj, owner=owner, tracked=tracked, stratum=stratum,
            codelibs=int(owner == "codelibs"), n_artifacts=len(last_pre), rel_per_year_pre=round(len(pre) / 2.0, 2),
            bom_pre=int(any(x["bom"] for x in last_pre.values() if x["v"])),
            age_years_at_event=round((date.fromisoformat(e["event"]) - date.fromisoformat(min(dated))).days / 365.25, 2),
            active_post=int(bool(post)), outcome=r8.get("outcome_2024_11", ""),
            switcher=int(g == "es" and r8.get("outcome_2024_11", "") in ("switch", "dual", "removed"))))
        split = (lambda v: vt(v) > (7, 10, 2)) if g == "es" else None
        rows += build_quarters("es", g, proj, rs, tracked, idx[tracked], minors, sup, split,
                               lambda xs: dict(any_fork=int(any(t["x"].get("os") for t in xs)),
                                               any_agpl=int(any(t["x"].get("agpl") for t in xs))))
    return projects, rows


ap, ar = build_akka()
ep, er = build_es()
pj, pq = pd.DataFrame(ap + ep), pd.DataFrame(ar + er)
# ES switcher flag also catches projects that declared OpenSearch in any post-event quarter
os_post = set(pq[(pq.event == "es") & (pq.period == "post") & (pq.any_fork == 1)].project)
pj.loc[(pj.event == "es") & (pj.treated == 1) & pj.project.isin(os_post), "switcher"] = 1
pj.to_csv(O / "projects.csv", index=False)
pq.to_csv(O / "panel.csv", index=False)
summary = {}
for ev in ("akka", "es"):
    p, q = pj[pj.event == ev], pq[(pq.event == ev) & pq.M1.notna()]
    summary[ev] = dict(
        projects=p.groupby("group").size().to_dict(), active=p.groupby("group").active_post.sum().to_dict(),
        project_quarters_M1=q.groupby(["group", "period"]).size().unstack().fillna(0).astype(int).to_dict(),
        M1_mean=q.groupby(["group", "period"]).M1.mean().round(3).unstack().to_dict(),
        M1s_nonmissing_share=round(float(q.M1s.notna().mean()), 3),
        switchers_treated=int(p[p.treated == 1].switcher.sum()))
(O / "panel_summary.json").write_text(json.dumps(summary, indent=1, default=str))
print(json.dumps(summary, indent=1, default=str))
