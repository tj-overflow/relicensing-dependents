"""Step 15g (R4): estimates for C1 (non-competing benchmarks) and C2 (downstream exposure).

C1  For each kept benchmark (outputs/step15/r4_benchmarks.json), for the pooled kept set (deduplicated in step15f),
    and for Typelevel (Step 13b cohorts) for reference: LU-1 difference-in-differences against Akka A26/A27 on
    Y1 (active within 240 days) and Y1u (full risk set), ATT-weighted (each group's early cohort reweighted to its
    late cohort, as step13h) and unweighted; CR1 and the restricted wild cluster bootstrap for the weighted rows.
    Also each benchmark's own late - early contrast, and its shares.
    Extra row: pooled kept + Typelevel, a project
    in both kept once in the Typelevel set.
C2  exposure_i = distinct packages outside project i with a release in [L-365, L) declaring any package of i as a
    direct non-test dependency (data/raw/step15/exposure.csv). Stacked A26 + A27 (A26 reweighted to A27, as E1):
    outcome ~ a27 + lexp + a27*lexp, lexp = log(1 + exposure); outcomes adopt240 (predicted < 0) and freeze240
    (predicted > 0). Elasticsearch (secondary): treated projects in the Step 11 panel, M1 on project and quarter
    fixed effects plus Post*lexp (exposure in [2020-01-14, 2021-01-14)); M1_restr reported as well.
Outputs: outputs/step15/r4_estimates.json, bench_shares.csv, exposure_projects.csv
"""
import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
O, LU, RAW = ROOT / "outputs/step15", ROOT / "outputs/step13/lu", ROOT / "data/raw/step15"
src = (ROOT / "scripts/step13h_lu_estimate.py").read_text(encoding="utf-8")
ns = {"__file__": str(ROOT / "scripts/step13h_lu_estimate.py")}
exec(src.split("\nAK = [")[0], ns)
att_weights, wls_cl, wcb, SEED = ns["att_weights"], ns["wls_cl"], ns["wcb"], ns["SEED"]


def raw_open(path):
    """Open a raw extract, or its .gz copy (the replication package ships large extracts gzipped)."""
    import gzip
    path = Path(path)
    if path.exists():
        return open(path, encoding="utf-8")
    return gzip.open(str(path) + ".gz", "rt", encoding="utf-8")


def prep(d):
    d = d.copy()
    d["l_rel"], d["l_art"], d["l_since"] = np.log1p(d.releases_pre), np.log1p(d.artifacts_pre), np.log1p(d.days_since_change)
    d["late"] = (d.period == "late").astype(int)
    d["akka"] = (d.group == "akka").astype(int)
    return d


def fit(d, y, terms, j, w, boot):
    X = np.column_stack([np.ones(len(d))] + [d[t].values for t in terms]).astype(float)
    yy = d[y].values.astype(float)
    g = pd.factorize(d.owner)[0]
    b, se, G = wls_cl(yy, X, w, g)
    r = dict(coef=round(float(b[j]), 4), se=round(float(se[j]), 4),
             ci95=[round(float(b[j] - 1.96 * se[j]), 4), round(float(b[j] + 1.96 * se[j]), 4)], n=int(len(d)), owners=int(G))
    if boot:
        r["p_wcb"] = round(wcb(yy, X, w, g, j, np.random.default_rng(SEED)), 4)
    return r


AK = prep(pd.read_csv(LU / "cohorts.csv"))
akka = AK[AK.cohort.isin(["A26", "A27"])]
TL = AK[AK.cohort.isin(["F21", "C21", "F34", "C34"])].assign(bench="typelevel")
BC = prep(pd.read_csv(O / "bench_cohorts.csv"))
info = json.loads((O / "r4_benchmarks.json").read_text())
sets = {lib: BC[BC.library == lib].assign(bench=lib) for lib in info["kept"]}
sets["pooled_kept"] = BC[BC.pooled == 1].assign(bench="pooled_kept")
pk = BC[BC.pooled == 1]
tl_keys = set(zip(TL.period, TL.project))
sets["pooled_kept_plus_typelevel"] = pd.concat([TL, pk[[k not in tl_keys for k in zip(pk.period, pk.project)]]]).assign(bench="pooled_plus_tl")
sets["typelevel"] = TL

out, share_rows = {"C1": {}}, []
for name, b in sets.items():
    res = {}
    for ycol, cond in (("y1", "act240"), ("y1u", None)):
        d = pd.concat([akka, b], ignore_index=True)
        if cond:
            d = d[d[cond] == 1]
        d = d.dropna(subset=[ycol]).reset_index(drop=True)
        d["ak_late"] = d.akka * d.late
        for wt in (True, False):
            w = att_weights(d, "late").values if wt else np.ones(len(d))
            tag = "weighted" if wt else "unweighted"
            res[f"{ycol}_DiD_{tag}"] = fit(d, ycol, ["akka", "late", "ak_late"], 3, w, boot=wt)
        bb = d[d.akka == 0].reset_index(drop=True)
        res[f"{ycol}_bench_late_minus_early_weighted"] = fit(bb, ycol, ["late"], 1, att_weights(bb, "late").values, False)
    out["C1"][name] = res
    for p, g in b.groupby("period"):
        share_rows.append(dict(bench=name, period=p, n=len(g), act240=round(g.act240.mean(), 4),
                               y1_active=round(g.loc[g.act240 == 1, "y1"].mean(), 4), y1u=round(g.y1u.mean(), 4)))
    print(name, {k: (v["coef"], v["ci95"], v.get("p_wcb")) for k, v in res.items() if "DiD" in k}, flush=True)
pd.DataFrame(share_rows).to_csv(O / "bench_shares.csv", index=False)

# ---------------- C2: exposure ----------------
head = (ROOT / "scripts/step13g_lu_build.py").read_text(encoding="utf-8").split("\ncore, avail = set()")[0]
ns2 = {"__file__": str(ROOT / "scripts/step13g_lu_build.py")}
exec(head, ns2)
norm_repo = ns2["norm_repo"]
scm = {}
allpk = []
for r in csv.DictReader(open(ROOT / "data/raw/step04/releases.csv", encoding="utf-8")):
    allpk.append(r["package"])
    if r["scm"]:
        scm[r["package"]] = r["scm"]
pk2proj = {p: norm_repo(scm.get(p), p) for p in set(allpk)}
es = pd.read_csv(ROOT / "outputs/step08/es_project_panel.csv", usecols=["project", "package"]).drop_duplicates()
for p, pr in zip(es.package, es.project):
    pk2proj.setdefault(p, pr)
hits = defaultdict(list)  # target project -> [(published, dependent package, dependent project)]
for r in csv.DictReader(raw_open(RAW / "exposure.csv")):
    if not r["published"]:
        continue
    dproj = norm_repo(r["source_repo"] or None, r["package"])
    for t in {pk2proj.get(x) for x in r["targets"].split(";") if x}:
        if t and t != dproj:
            hits[t].append((r["published"][:10], r["package"]))


def exposure(proj, L):
    lo = (pd.Timestamp(L) - pd.Timedelta(days=365)).strftime("%Y-%m-%d")
    return len({p for d, p in hits.get(proj, []) if lo <= d < L})


LAUNCH = {"A24": "2015-09-30", "A25": "2017-04-12", "A26": "2019-11-06", "A27": "2022-10-19"}
A = pd.concat([AK[AK.group == "akka"], prep(pd.read_csv(LU / "cohorts_a24.csv"))], ignore_index=True)
A["exposure"] = [exposure(p, LAUNCH[c]) for p, c in zip(A.project, A.cohort)]
A["lexp"] = np.log1p(A.exposure)
for h in (240,):
    adopt = A.adopt_days.notna() & (A.adopt_days <= h)
    A[f"adopt{h}"] = adopt.astype(int)
    A[f"freeze{h}"] = (~adopt & (A[f"act{h}"] == 1) & (A[f"old{h}"] == 1)).astype(int)
A[["cohort", "project", "exposure"]].to_csv(O / "exposure_projects.csv", index=False)
c2 = {"exposure_by_cohort": A.groupby("cohort").exposure.describe().round(2).to_dict(orient="index")}
d = A[A.cohort.isin(["A26", "A27"])].reset_index(drop=True)
d["a27"] = (d.cohort == "A27").astype(int)
d["a27_lexp"] = d.a27 * d.lexp
w = att_weights(d.assign(late=d.a27), "late").values
for y in ("adopt240", "freeze240"):
    c2[f"{y}_interaction_weighted"] = fit(d, y, ["a27", "lexp", "a27_lexp"], 3, w, boot=True)
    c2[f"{y}_interaction_unweighted"] = fit(d, y, ["a27", "lexp", "a27_lexp"], 3, np.ones(len(d)), boot=False)
    c2[f"{y}_lexp_main_weighted"] = fit(d, y, ["a27", "lexp", "a27_lexp"], 2, w, boot=False)

# Elasticsearch, secondary
P = pd.read_csv(ROOT / "outputs/step11/panel.csv")
P = P[(P.event == "es") & (P.treated == 1) & P.period.isin(["pre", "post"])].dropna(subset=["M1"]).copy()
P["exposure"] = [exposure(p, "2021-01-14") for p in P.project]
P["lexp"] = np.log1p(P.exposure)
P["post_lexp"] = (P.period == "post").astype(int) * P.lexp
for ycol in ("M1", "M1_restr"):
    q = P.dropna(subset=[ycol]).copy()
    for col in (ycol, "post_lexp"):  # two-way within transformation (balanced enough; iterate to convergence)
        q[col + "_dm"] = q[col].astype(float)
        for _ in range(50):
            q[col + "_dm"] -= q.groupby("project")[col + "_dm"].transform("mean")
            q[col + "_dm"] -= q.groupby("quarter")[col + "_dm"].transform("mean")
    X = q[["post_lexp_dm"]].values
    g = pd.factorize(q.owner)[0]
    b, se, G = wls_cl(q[ycol + "_dm"].values, X, np.ones(len(q)), g)
    c2[f"es_{ycol}_post_x_lexp"] = dict(coef=round(float(b[0]), 4), se=round(float(se[0]), 4),
                                        ci95=[round(float(b[0] - 1.96 * se[0]), 4), round(float(b[0] + 1.96 * se[0]), 4)],
                                        n=int(len(q)), projects=int(q.project.nunique()), owners=int(G),
                                        note="SE not corrected for absorbed fixed effects (conservative df ignored)")
c2["es_exposure"] = P.drop_duplicates("project").exposure.describe().round(2).to_dict()
out["C2"] = c2
(O / "r4_estimates.json").write_text(json.dumps(out, indent=1, default=str))
print(json.dumps({k: v for k, v in c2.items() if k != "exposure_by_cohort"}, indent=1, default=str))
print(c2["exposure_by_cohort"])
