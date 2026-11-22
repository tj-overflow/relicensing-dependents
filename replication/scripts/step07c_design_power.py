"""Step 7c: E1 design diagnostics and power (no E1 point estimate is computed here).

Population: active, non-vendor projects (risk_set_v2). Treatment month T_i from treatment_dates.csv.
  1. Timing variation: cohorts (month and quarter of T_i), never-treated count.
  2. Exogeneity: among treated, regress T_i (months since 2023-07) on predetermined characteristics,
     with and without module-composition indicators; joint Wald tests (owner-clustered).
     Demand check: Spearman correlation between an upstream library's port date and its number of
     risk-set dependents.
  3. Power for E1 by placebo permutation: the outcome is the real first-switch month; treatment dates are
     randomly permuted across projects (keeping their distribution), the hazard LPM
         switch_it ~ month FE + 1[t >= T_i]   (project-months at risk, owner-clustered)
     is re-estimated 500 times; SD of the placebo coefficients = SE under the null; MDE = 2.8 x SE.
     The real-assignment coefficient is NOT computed.
  4. MDEs for E2 (analytic, A1 split from the Step 5 sample) and E3 (Step 6 SEs).
Outputs: outputs/step07/design_power.json
"""
import csv
import json
import math
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
O = ROOT / "outputs/step07"
rng = np.random.default_rng(20230710)
td = pd.read_csv(O / "treatment_dates.csv", dtype=str).fillna("")
td = td[td.active_post == "1"].copy()
cov = pd.read_csv(ROOT / "outputs/step06/cmp_risk_set.csv")
cov = cov[cov.group == "akka"].set_index("project")
td = td.join(cov[["rel_per_year_pre", "n_artifacts", "age_years_at_event"]], on="project")
res = {"n_active_nonvendor": len(td)}


def mon(d):
    return int(d[:4]) * 12 + int(d[5:7]) - 1 if d else None


M0 = mon("2023-07-01")
td["T"] = td["T_all"].map(lambda d: mon(d) if d and d != "n/a" else None)
td["Tq"] = td["T_all"].map(lambda d: f"{d[:4]}Q{(int(d[5:7]) - 1) // 3 + 1}" if d and d != "n/a" else "never")
res["cohorts_quarter"] = dict(sorted(Counter(td.Tq).items()))
res["cohorts_month"] = dict(sorted(Counter(td["T_all"].str[:7].replace("", "never")).items()))
qc = Counter(td.Tq)
res["quarter_cohorts_with_ge10"] = sum(1 for k, v in qc.items() if k != "never" and v >= 10)
mc = Counter(td["T_all"].str[:7])
res["month_cohorts_with_ge10"] = sum(1 for k, v in mc.items() if k and v >= 10)
res["never_treated_by_horizon"] = int((td.Tq == "never").sum())
res["T_first_party_only_cohorts_quarter"] = dict(sorted(Counter(
    td.T_first_party.map(lambda d: f"{d[:4]}Q{(int(d[5:7]) - 1) // 3 + 1}" if d else "never")).items()))
res["projects_with_third_party_upstreams"] = int((td.n_upstreams.astype(int) > 0).sum())
res["T_set_by_third_party"] = int(((td.T_third_party != "n/a") & (td.T_third_party != "") &
                                   (td.T_third_party > td.T_first_party)).sum())

# 2. exogeneity among treated
tr = td[td["T"].notna()].copy()
tr["Tm"] = tr["T"] - M0
tr["log_rel"] = np.log1p(tr.rel_per_year_pre.astype(float))
tr["log_art"] = np.log1p(tr.n_artifacts.astype(float))
tr["scala3"] = tr.scala3_pre_event.astype(int)
tr["provided"] = tr.akka_provided_or_testkit_only.astype(int)
for g in ("http", "persistence", "cluster", "connectors"):
    tr[g] = tr.akka_modules_pre.str.contains(g).astype(int)
tr = tr.dropna(subset=["log_rel", "log_art", "age_years_at_event"])
grp = pd.factorize(tr.owner)[0]
ex = {}
for lab, f, test in (("predetermined only", "Tm ~ log_rel + log_art + scala3 + age_years_at_event + provided",
                      ["log_rel", "log_art", "scala3", "age_years_at_event", "provided"]),
                     ("with module composition", "Tm ~ log_rel + log_art + scala3 + age_years_at_event + provided"
                      " + http + persistence + cluster + connectors",
                      ["log_rel", "log_art", "scala3", "age_years_at_event", "provided"])):
    fit = smf.ols(f, data=tr).fit(cov_type="cluster", cov_kwds={"groups": grp})
    R = np.zeros((len(test), len(fit.params)))
    for i, n in enumerate(test):
        R[i, list(fit.params.index).index(n)] = 1
    w = fit.wald_test(R, scalar=True)
    ex[lab] = dict(n=int(len(tr)), joint_chi2=round(float(w.statistic), 3), joint_p=round(float(w.pvalue), 4),
                   r2=round(fit.rsquared, 3),
                   coefs={k: [round(fit.params[k], 3), round(fit.pvalues[k], 3)] for k in fit.params.index if k != "Intercept"})
comp = smf.ols("Tm ~ http + persistence + cluster + connectors", data=tr).fit()
ex["module composition alone R2"] = round(comp.rsquared, 3)
res["exogeneity"] = ex

up = pd.read_csv(O / "upstreams.csv", dtype=str).fillna("")
if len(up):
    g = up.groupby("upstream").agg(n_dependents=("project", "nunique"), port=("port_date", "first"))
    g = g[g.port != ""]
    g["port_m"] = g.port.map(mon)
    if len(g) > 3:
        rho, p = spearmanr(g.n_dependents, g.port_m)
        res["demand_check_upstream_port_vs_dependents"] = dict(n_upstreams_ported=int(len(g)),
                                                               spearman_rho=round(float(rho), 3), p=round(float(p), 4))
    res["upstreams_total"] = int(up.upstream.nunique())
    res["upstreams_never_ported"] = int(up[up.port_date == ""].upstream.nunique())

# 3. placebo power for E1
months = list(range(mon("2022-09-01"), mon("2025-09-01") + 1))
sw = td["first_switch_v2"].map(mon).tolist()
owners = td.owner.tolist()
Ts = td["T"].tolist()
base_rows = []
for i in range(len(td)):
    for t in months:
        if sw[i] is not None and t > sw[i]:
            break
        base_rows.append((i, t, int(sw[i] == t)))
B = pd.DataFrame(base_rows, columns=["i", "t", "y"])
B["owner"] = [owners[i] for i in B.i]
grp = pd.factorize(B.owner)[0]
Tfill = np.array([np.inf if (x is None or (isinstance(x, float) and math.isnan(x))) else x for x in Ts])


def est(Tvec):
    B["D"] = (B.t.values >= Tvec[B.i.values]).astype(int)
    f = smf.ols("y ~ C(t) + D", data=B).fit()
    return f.params["D"]


draws = [est(rng.permutation(Tfill)) for _ in range(500)]
se0 = float(np.std(draws))
h0 = B.y.mean()
res["E1_power"] = dict(project_months_at_risk=int(len(B)), monthly_switch_hazard=round(h0, 4),
                       placebo_se_monthly=round(se0, 4), mde_monthly_hazard=round(2.8 * se0, 4),
                       mde_12m_cumulative_approx=round(1 - (1 - h0 - 2.8 * se0) ** 12 - (1 - (1 - h0) ** 12), 3),
                       placebo_mean=round(float(np.mean(draws)), 4), reps=500,
                       note="hazard LPM; owner clustering affects inference but the permutation SD is the null spread")

# 4. E2 and E3 MDEs
p = (td.outcome_v2.isin(["switch", "dual_or_partial"])).mean()
n = len(td)
share_a1 = 32 / 54  # A1 = 1 share in the Step 5 hand-coded sample (non-foundation)
n1, n0 = n * share_a1, n * (1 - share_a1)
m = n / td.owner.nunique()
deff = 1 + (m - 1) * 0.3
se2 = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n0) * deff)
res["E2_mde"] = dict(switch_or_dual_share=round(p, 3), n=n, share_exposed_A1=round(share_a1, 3),
                     avg_projects_per_owner=round(m, 2), icc_assumed=0.3, mde=round(2.8 * se2, 3),
                     mde_with_misclassification=round(2.8 * se2 / (2 * 0.778 - 1), 3),
                     note="the misclassification line scales by 1/(2*agreement-1), a nondifferential binary error bound")
s6 = json.loads((ROOT / "outputs/step06/did_descriptive.json").read_text())
s6b = json.loads((ROOT / "outputs/step06/did_balanced_nonswitchers.json").read_text())
res["E3_mde"] = dict(all=round(2.8 * s6["M1 all"]["se"], 3), balanced_nonswitchers=round(2.8 * s6b["M1"]["se"], 3))
(O / "design_power.json").write_text(json.dumps(res, indent=1, default=str))
print(json.dumps(res, indent=1, default=str))
