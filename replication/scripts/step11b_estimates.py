"""Step 11b: main panel estimates, numbered 5.1-5.5.

5.1 primary   Y = project FE + quarter FE + beta*Treated*Post; ATT weights; owner clusters; pre and post periods
              (event quarter excluded). Y = M1 (primary for Akka); M3 secondary.
5.2 event study  Treated x quarter for every quarter except the last pre-event quarter; joint pre-test and
                 linear pre-trend difference.
5.3 balanced non-switchers  treated projects that never switch/dual/remove, with >=1 tracked-line quarter
                 before and after; comparison projects with >=1 before and after.
5.4 Elasticsearch strata  all, excluding CodeLibs, client, embedded.
5.5 cross-event difference Delta = beta_Akka - beta_ES.
Also reports a statsmodels dummy-variable check of the primary estimate.
Outputs: outputs/step11/estimates.json, balance.csv, event_study.csv
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

sys.path.insert(0, str(Path(__file__).resolve().parent))
import step11_est as E  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
O = ROOT / "outputs/step11"
pj = pd.read_csv(O / "projects.csv")
pq = pd.read_csv(O / "panel.csv")
REF = {"akka": "2022Q2", "es": "2020Q4"}
res, bal_rows, es_rows = {}, [], []

W = {}
for ev in ("akka", "es"):
    b, trimmed = E.weights(pj, ev)
    W[ev] = b
    for r in E.smd_table(b, ev):
        bal_rows.append(dict(event=ev, **r))
    res[f"weights {ev}"] = dict(projects=int(len(b) + trimmed), trimmed=trimmed,
                                ps_range_treated=[round(b[b.treated == 1].ps.min(), 3), round(b[b.treated == 1].ps.max(), 3)],
                                ps_range_cmp=[round(b[b.treated == 0].ps.min(), 3), round(b[b.treated == 0].ps.max(), 3)])
pd.DataFrame(bal_rows).to_csv(O / "balance.csv", index=False)


def sample(ev, m, periods=("pre", "post"), sub=None):
    b = W[ev]
    d = pq[(pq.event == ev) & pq.period.isin(periods) & pq[m].notna()].merge(
        b[["project", "group", "w", "stratum" if ev == "es" else "http_user", "switcher"] + (["codelibs"] if ev == "es" else [])],
        on=["project", "group"], how="inner")
    if sub is not None:
        d = sub(d)
    d["D"] = d.treated * (d.period == "post")
    return d


def balanced(d):
    keep = d.groupby("project").period.agg(lambda s: {"pre", "post"} <= set(s))
    d = d[d.project.isin(keep[keep].index)]
    return d[(d.treated == 0) | (d.switcher == 0)]


STRATA = {"akka": {"all": None},
          "es": {"all": None, "excl_codelibs": lambda d: d[d.codelibs == 0],
                 "client": lambda d: d[d.stratum == "client"], "embedded": lambda d: d[d.stratum == "embedded"]}}

for ev in ("akka", "es"):
    for lab, sub in STRATA[ev].items():
        for m in ("M1", "M3"):
            d = sample(ev, m, sub=sub)
            f = E.twfe(d, m, ["D"], w=d.w)
            res[f"5.1 {ev} {lab} {m}"] = E.summary(f, "D", dict(
                n_treated=int(d[d.treated == 1].project.nunique()), n_cmp=int(d[d.treated == 0].project.nunique()),
                mean_treated_pre=round(float(d[(d.treated == 1) & (d.period == "pre")][m].mean()), 3)))
            db = balanced(d)
            fb = E.twfe(db, m, ["D"], w=db.w)
            res[f"5.3 {ev} {lab} {m} balanced_nonswitchers"] = E.summary(fb, "D", dict(
                n_treated=int(db[db.treated == 1].project.nunique()), n_cmp=int(db[db.treated == 0].project.nunique())))
        # 5.2 event study (M1)
        d = sample(ev, "M1", periods=("pre", "event", "post"), sub=sub)
        qs = sorted(q for q in d.quarter.unique() if q != REF[ev])
        cols = []
        for q in qs:
            c = "Dq_" + q
            d[c] = d.treated * (d.quarter == q)
            cols.append(c)
        f = E.twfe(d, "M1", cols, w=d.w)
        pre_idx = [i for i, q in enumerate(qs) if d[d.quarter == q].period.iloc[0] == "pre"]
        F, p = E.wald(f, pre_idx)
        for i, q in enumerate(qs):
            es_rows.append(dict(event=ev, sample=lab, quarter=q, period=d[d.quarter == q].period.iloc[0],
                                coef=f.beta[i], se=f.se[i]))
        es_rows.append(dict(event=ev, sample=lab, quarter=REF[ev], period="pre", coef=0.0, se=0.0))
        dp = sample(ev, "M1", periods=("pre",), sub=sub)
        order = {q: i for i, q in enumerate(sorted(dp.quarter.unique()))}
        dp["Dt"] = dp.treated * dp.quarter.map(order)
        ft = E.twfe(dp, "M1", ["Dt"], w=dp.w)
        res[f"5.2 {ev} {lab} event_study"] = dict(
            joint_pre_F=round(F, 3), joint_pre_p=round(p, 4), df=len(pre_idx),
            linear_pretrend=E.summary(ft, "Dt"),
            post_mean_coef=round(float(np.mean([f.beta[i] for i, q in enumerate(qs) if d[d.quarter == q].period.iloc[0] == "post"])), 4))

# 5.5 cross-event difference
for lab in ("all", "excl_codelibs"):
    a, e = res["5.1 akka all M1"], res[f"5.1 es {lab} M1"]
    delta, se = a["coef"] - e["coef"], float(np.hypot(a["se"], e["se"]))
    res[f"5.5 delta akka_all - es_{lab} M1"] = dict(delta=round(delta, 4), se=round(se, 4),
                                                    ci95=[round(delta - 1.96 * se, 4), round(delta + 1.96 * se, 4)])
owners_a = set(pj[(pj.event == "akka") & (pj.treated == 1)].owner.str.lower())
owners_e = set(pj[(pj.event == "es") & (pj.treated == 1)].owner.str.lower())
res["5.5 treated owner overlap"] = sorted(owners_a & owners_e)

# check: dummy-variable regression with statsmodels for the primary estimate
d = sample("akka", "M1")
chk = smf.wls("M1 ~ D + C(project) + C(quarter)", data=d, weights=d.w).fit(
    cov_type="cluster", cov_kwds={"groups": pd.factorize(d.owner)[0]})
res["check statsmodels dummies akka M1"] = dict(coef=round(float(chk.params["D"]), 4), se=round(float(chk.bse["D"]), 4))

pd.DataFrame(es_rows).sort_values(["event", "sample", "quarter"]).to_csv(O / "event_study.csv", index=False)
(O / "estimates.json").write_text(json.dumps(res, indent=1))
print(json.dumps(res, indent=1))
