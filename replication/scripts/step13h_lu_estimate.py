"""Step 13h: estimates for the line-launch uptake design.

LU-1 (primary): Y = a + b Akka + c Late + theta_DD Akka x Late, stacked project-cohort data (A26, A27, comparison
  early = fs2 2.1 / cats-effect 2.1, late = fs2 3.4 / cats-effect 3.4).
LU-2: theta_A = U(A27) - U(A26).   LU-3: projects in both A26 and A27 samples, exact McNemar.
LU-P: U(A26) - U(A25), unweighted and reweighted.
Weights: within each supplier group, the earlier cohort is reweighted to the later cohort's covariates (ATT odds
  p/(1-p) from a logit of cohort membership, p trimmed to [0.05, 0.95]); later cohort weight 1. The logit is fitted on
  the estimation sample of each outcome. Covariates: log1p(releases_pre), log1p(artifacts_pre), any_213, age_years,
  log1p(days_since_change); Akka adds clpe and http. Constant covariates are dropped.
Inference: owner-clustered CR1 SE; wild cluster bootstrap (restricted, Rademacher, 9,999 draws, seed 20261111).
Outcomes: y1 (primary), y1u, y1_365, act240 (sample: full risk set). Y2 and Kaplan-Meier curves descriptive.
Unweighted versions and per-library comparisons are reported as well.
Outputs: outputs/step13/lu/estimates.json, km.csv, shares.csv
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import binomtest

ROOT = Path(__file__).resolve().parents[1]
O = ROOT / "outputs/step13/lu"
D = pd.read_csv(O / "cohorts.csv")
D["late"] = (D.period == "late").astype(int)
D["akka"] = (D.group == "akka").astype(int)
B = 9999
SEED = 20261111
COV = ["l_rel", "l_art", "any_213", "age_years", "l_since"]
D["l_rel"], D["l_art"], D["l_since"] = np.log1p(D.releases_pre), np.log1p(D.artifacts_pre), np.log1p(D.days_since_change)
SAMPLE = {"y1": "act240", "y1u": None, "y1_365": "act365", "act240": None}


def att_weights(d, treat_col):
    """ATT odds weights reweighting treat_col == 0 to treat_col == 1, within supplier group."""
    w = pd.Series(1.0, index=d.index)
    for g, x in d.groupby("group"):
        cov = COV + (["clpe", "http"] if g == "akka" else [])
        cov = [c for c in cov if x[c].std() > 0]
        Z = (x[cov] - x[cov].mean()) / x[cov].std()
        Z = sm.add_constant(Z)
        try:
            p = sm.Logit(x[treat_col], Z).fit(disp=0).predict(Z)
        except Exception:
            p = sm.Logit(x[treat_col], Z).fit_regularized(disp=0, alpha=0.1).predict(Z)
        p = p.clip(0.05, 0.95)
        w.loc[x.index] = np.where(x[treat_col] == 1, 1.0, p / (1 - p))
    return w


def wls_cl(y, X, w, g):
    sw = np.sqrt(w)
    Xw, yw = X * sw[:, None], y * sw
    XtX = np.linalg.inv(Xw.T @ Xw)
    b = XtX @ Xw.T @ yw
    e = yw - Xw @ b
    G = int(g.max()) + 1  # g: integer cluster codes 0..G-1
    S = np.zeros((G, X.shape[1]))
    np.add.at(S, g, Xw * e[:, None])
    meat = S.T @ S
    n, k = X.shape
    V = XtX @ meat @ XtX * G / (G - 1) * (n - 1) / (n - k)
    return b, np.sqrt(np.diag(V)), G


def wcb(y, X, w, g, j, rng):
    """Restricted wild cluster bootstrap p for coefficient j."""
    b, se, _ = wls_cl(y, X, w, g)
    t0 = b[j] / se[j]
    Xr = np.delete(X, j, axis=1)
    sw = np.sqrt(w)
    br = np.linalg.lstsq(Xr * sw[:, None], y * sw, rcond=None)[0]
    fit, res = Xr @ br, y - Xr @ br
    G = int(g.max()) + 1
    ts = np.empty(B)
    for i in range(B):
        v = rng.choice([-1.0, 1.0], size=G)[g]
        bb, ss, _ = wls_cl(fit + res * v, X, w, g)
        ts[i] = bb[j] / ss[j]
    return float(np.mean(np.abs(ts) >= abs(t0)))


def est(d, ycol, terms, j, weighted, wcol, boot=True):
    d = d.copy()
    w = att_weights(d, wcol).values if weighted else np.ones(len(d))
    X = np.column_stack([np.ones(len(d))] + [d[t].values for t in terms]).astype(float)
    y = d[ycol].values.astype(float)
    g = pd.factorize(d.owner)[0]
    b, se, G = wls_cl(y, X, w, g)
    r = dict(coef=round(float(b[j]), 4), se=round(float(se[j]), 4),
             ci95=[round(float(b[j] - 1.96 * se[j]), 4), round(float(b[j] + 1.96 * se[j]), 4)],
             n=int(len(d)), owners=int(G))
    if boot:
        r["p_wcb"] = round(wcb(y, X, w, g, j, np.random.default_rng(SEED)), 4)
    return r


def sample(ycol, cohorts):
    d = D[D.cohort.isin(cohorts)]
    s = SAMPLE[ycol]
    if s:
        d = d[d[s] == 1]
    return d.dropna(subset=[ycol]).reset_index(drop=True)


AK = ["A26", "A27"]
CMP = ["F21", "C21", "F34", "C34"]
out = {}
for y in SAMPLE:
    dd = sample(y, AK + CMP)
    dd["ak_late"] = dd.akka * dd.late
    res = {}
    for wt in (True, False):
        tag = "weighted" if wt else "unweighted"
        res["LU1_" + tag] = est(dd, y, ["akka", "late", "ak_late"], 3, wt, "late", boot=(y == "y1" or wt))
        res["LU2_" + tag] = est(dd[dd.akka == 1].reset_index(drop=True), y, ["late"], 1, wt, "late", boot=(y == "y1" or wt))
    for lib, cs in (("cats_effect", ["C21", "C34"]), ("fs2", ["F21", "F34"])):
        x = sample(y, AK + cs)
        x["ak_late"] = x.akka * x.late
        res["LU1_weighted_" + lib + "_only"] = est(x, y, ["akka", "late", "ak_late"], 3, True, "late", boot=False)
    # placebo A26 vs A25: "late" = A26
    p = sample(y, ["A25", "A26"])
    p["late"] = (p.cohort == "A26").astype(int)
    res["LUP_unweighted"] = est(p, y, ["late"], 1, False, "late", boot=False)
    res["LUP_weighted"] = est(p, y, ["late"], 1, True, "late", boot=False)
    out[y] = res
    print(y, json.dumps({k: (v["coef"], v["ci95"], v.get("p_wcb")) for k, v in res.items()}), flush=True)

# LU-3: paired, projects in both A26 and A27 y1 samples
a = sample("y1", ["A26"]).set_index("project").y1
b = sample("y1", ["A27"]).set_index("project").y1
both = a.index.intersection(b.index)
n10 = int(((a[both] == 1) & (b[both] == 0)).sum())
n01 = int(((a[both] == 0) & (b[both] == 1)).sum())
out["LU3_paired_y1"] = dict(n=len(both), adopt_A26_only=n10, adopt_A27_only=n01,
                            both=int(((a[both] == 1) & (b[both] == 1)).sum()),
                            neither=int(((a[both] == 0) & (b[both] == 0)).sum()),
                            diff=round((n01 - n10) / len(both), 4) if len(both) else None,
                            p_mcnemar_exact=round(binomtest(n01, n01 + n10).pvalue, 4) if n01 + n10 else None)
# shares by cohort
sh = []
for c in ["A25", "A26", "A27"] + CMP:
    x = D[D.cohort == c]
    sh.append(dict(cohort=c, risk_set=len(x), act240=round(x.act240.mean(), 4), act365=round(x.act365.mean(), 4),
                   n_y1=int(x.y1.notna().sum()), y1=round(x.y1.mean(), 4), y1u=round(x.y1u.mean(), 4),
                   y1_365=round(x.y1_365.mean(), 4), y2=round(x.y2.mean(), 4) if x.y2.notna().any() else None))
sh = pd.DataFrame(sh)
sh.to_csv(O / "shares.csv", index=False)
print(sh.to_string(index=False))
# pooled comparison shares per period
for per in ("early", "late"):
    x = D[(D.group == "cmp") & (D.period == per)]
    out[f"cmp_{per}_shares"] = dict(risk_set=len(x), act240=round(x.act240.mean(), 4), n_y1=int(x.y1.notna().sum()),
                                    y1=round(x.y1.mean(), 4), y1u=round(x.y1u.mean(), 4))
print(out["cmp_early_shares"], out["cmp_late_shares"])
print("LU3", out["LU3_paired_y1"])
# Kaplan-Meier over 365 days, sample act365; event = adopt_days, censor = last_rel_days
km = []
for c in ["A25", "A26", "A27", "CMP_early", "CMP_late"]:
    x = D[(D.cohort == c) if c.startswith("A") else ((D.group == "cmp") & (D.period == c.split("_")[1]))]
    x = x[x.act365 == 1]
    t = np.where(x.adopt_days.notna(), x.adopt_days, x.last_rel_days).astype(float)
    e = x.adopt_days.notna().values
    S = 1.0
    for day in range(0, 366):
        n_risk = int((t >= day).sum())
        d_ev = int(((t == day) & e).sum())
        if n_risk:
            S *= 1 - d_ev / n_risk
        if day % 30 == 0 or day in (240, 365):
            km.append(dict(cohort=c, day=day, adopted=round(1 - S, 4), at_risk=n_risk))
pd.DataFrame(km).to_csv(O / "km.csv", index=False)
(O / "estimates.json").write_text(json.dumps(out, indent=1))
