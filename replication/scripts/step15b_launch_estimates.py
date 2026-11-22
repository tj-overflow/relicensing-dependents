"""Step 15b (R3): within-Akka launch contrasts, Lee bounds, four-way outcomes and diagnostics (paper Section 5, Table 3).

Sections:
  2  four-way outcome (Adopt / Freeze / Leave / Inactive) at h = 240, 365, full risk set
  3  E1, E2, E3 (stacked; x1 = 1{A26} + 2*1{A27}, x2 = 1{A27}), E3s, E1c-E3c (conditional on act240), E6, E5 (repeat)
     weights: A25 and A26 each reweighted to A27 composition (ATT odds, LU-2 covariates, trimming as step13h)
     inference: owner CR1; restricted wild cluster bootstrap (9,999, Rademacher, seed 20261111) for E1, E2, E3.
     A wild-bootstrap "interval excluding zero" is read as p_wcb < 0.05 (test inversion at zero).
  3  E7 Lee-type trimming bounds (unweighted), owner-cluster bootstrap 2,000 draws, seed 20261112
  4  A24 (Akka 2.4.0) if >= 30 active within 240 days; E8 = Adopt240(A27) - linear prediction from A24, A25, A26
  5  activity diagnostics (descriptive)
  6  checks behind the paper's claims
Helper functions (att_weights, wls_cl, wcb) are taken from step13h_lu_estimate.py, so they are identical.
Inputs: outputs/step13/lu/cohorts.csv, cohorts_a24.csv, aux_preline.csv, release_years.csv, estimates.json
Output: outputs/step15/launch_estimates.json, fourway_shares.csv, activity_continuation.csv
"""
from pathlib import Path
import json

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
LU, O = ROOT / "outputs/step13/lu", ROOT / "outputs/step15"
O.mkdir(parents=True, exist_ok=True)

# ---- helpers from step13h (definitions only, executed in their own namespace) ----
src = (ROOT / "scripts/step13h_lu_estimate.py").read_text(encoding="utf-8")
ns = {"__file__": str(ROOT / "scripts/step13h_lu_estimate.py"), "__name__": "h13"}
exec(src.split("\nAK = [")[0], ns)
att_weights, wls_cl, wcb, B, SEED = ns["att_weights"], ns["wls_cl"], ns["wcb"], ns["B"], ns["SEED"]

D = pd.concat([pd.read_csv(LU / "cohorts.csv"), pd.read_csv(LU / "cohorts_a24.csv")], ignore_index=True)
D["l_rel"], D["l_art"], D["l_since"] = np.log1p(D.releases_pre), np.log1p(D.artifacts_pre), np.log1p(D.days_since_change)
LAUNCH = {"A24": "2015-09-30", "A25": "2017-04-12", "A26": "2019-11-06", "A27": "2022-10-19"}

# ---- section 2: four-way outcome ----
for h in (240, 365):
    adopt = D.adopt_days.notna() & (D.adopt_days <= h)
    act = D[f"act{h}"] == 1
    D[f"adopt{h}"] = adopt.astype(int)
    D[f"freeze{h}"] = (~adopt & act & (D[f"old{h}"] == 1)).astype(int)
    D[f"leave{h}"] = (~adopt & act & (D[f"old{h}"] == 0)).astype(int)
    D[f"inactive{h}"] = (~act).astype(int)
    assert (D[[f"adopt{h}", f"freeze{h}", f"leave{h}", f"inactive{h}"]].sum(axis=1) == 1).all()
CLS = ["adopt", "freeze", "leave", "inactive"]
shares = (D.groupby("cohort")[[f"{c}{h}" for h in (240, 365) for c in CLS]].mean().round(4)
          .join(D.groupby("cohort").size().rename("n")))
shares.to_csv(O / "fourway_shares.csv")


def weights_to(d, target="A27"):
    """Each non-target cohort reweighted to the target's covariates (pairwise logit, ATT odds)."""
    w = pd.Series(1.0, index=d.index)
    for c in d.cohort.unique():
        if c == target:
            continue
        pair = d[d.cohort.isin([c, target])].copy()
        pair["t"] = (pair.cohort == target).astype(int)
        w.loc[pair.index[pair.cohort == c]] = att_weights(pair, "t").loc[pair.cohort == c]
    return w.values


def fit(d, y, X_cols, j, weighted, boot):
    w = weights_to(d) if weighted else np.ones(len(d))
    X = np.column_stack([np.ones(len(d))] + [d[c].values for c in X_cols]).astype(float)
    yy = d[y].values.astype(float)
    g = pd.factorize(d.owner)[0]
    b, se, G = wls_cl(yy, X, w, g)
    r = dict(coef=round(float(b[j]), 4), se=round(float(se[j]), 4),
             ci95=[round(float(b[j] - 1.96 * se[j]), 4), round(float(b[j] + 1.96 * se[j]), 4)],
             n=int(len(d)), owners=int(G))
    if boot:
        r["p_wcb"] = round(wcb(yy, X, w, g, j, np.random.default_rng(SEED)), 4)
    return r, b, se, w


out = {"n_risk_set": D.groupby("cohort").size().to_dict()}
GAP = {"A27-A26": 2.95, "A26-A25": 2.57}


def akka_series(y, cond=None, boot=True):
    """E1 (pair A26-A27), and E2, E3 from the stacked A25-A26-A27 regression."""
    res = {}
    for wt in (True, False):
        tag = "weighted" if wt else "unweighted"
        d = D[D.cohort.isin(["A26", "A27"])]
        if cond:
            d = d[d[cond] == 1]
        d = d.reset_index(drop=True).assign(a27=lambda x: (x.cohort == "A27").astype(int))
        res[f"E1_{tag}"] = fit(d, y, ["a27"], 1, wt, boot)[0]
        s = D[D.cohort.isin(["A25", "A26", "A27"])]
        if cond:
            s = s[s[cond] == 1]
        s = s.reset_index(drop=True)
        s["x1"] = (s.cohort == "A26").astype(int) + 2 * (s.cohort == "A27").astype(int)
        s["x2"] = (s.cohort == "A27").astype(int)
        r2, b, se, _ = fit(s, y, ["x1", "x2"], 1, wt, boot)
        r3 = fit(s, y, ["x1", "x2"], 2, wt, boot)[0]
        res[f"E2_{tag}"], res[f"E3_{tag}"] = r2, r3
        e3s = res[f"E1_{tag}"]["coef"] - GAP["A27-A26"] / GAP["A26-A25"] * r2["coef"]
        res[f"E3s_{tag}"] = dict(coef=round(e3s, 4), note="point estimate; E1 - (2.95/2.57) * E2")
    return res


# ---- section 3 ----
out["E_unconditional_h240"] = akka_series("adopt240")
out["E_unconditional_h365"] = akka_series("adopt365", boot=False)
out["E_conditional_h240"] = akka_series("adopt240", cond="act240")   # E1c, E2c, E3c
print("E (h240):", {k: (v["coef"], v.get("ci95"), v.get("p_wcb")) for k, v in out["E_unconditional_h240"].items()}, flush=True)
print("Ec (h240):", {k: (v["coef"], v.get("ci95"), v.get("p_wcb")) for k, v in out["E_conditional_h240"].items()}, flush=True)

e6 = {}
for h in (240, 365):
    for c in ["freeze", "leave", "inactive"]:
        for wt in (True, False):
            tag = "weighted" if wt else "unweighted"
            d = D[D.cohort.isin(["A26", "A27"])].reset_index(drop=True).assign(a27=lambda x: (x.cohort == "A27").astype(int))
            s = D[D.cohort.isin(["A25", "A26", "A27"])].reset_index(drop=True)
            s["x1"] = (s.cohort == "A26").astype(int) + 2 * (s.cohort == "A27").astype(int)
            s["x2"] = (s.cohort == "A27").astype(int)
            e6[f"{c}{h}_E1_{tag}"] = fit(d, f"{c}{h}", ["a27"], 1, wt, False)[0]
            e6[f"{c}{h}_E3_{tag}"] = fit(s, f"{c}{h}", ["x1", "x2"], 2, wt, False)[0]
out["E6"] = e6
prev = json.loads((LU / "estimates.json").read_text())
out["E5_repeat_from_step13h"] = {"y1u_LU1_weighted": prev["y1u"]["LU1_weighted"], "y1u_LU1_unweighted": prev["y1u"]["LU1_unweighted"]}


# ---- E7: Lee-type bounds (unweighted) ----
def lee_pair(d, later, earlier):
    """Bounds on adoption(later) - adoption(earlier) among the always-active, trimming the higher-activity cohort."""
    a, b = d[d.cohort.isin(later)], d[d.cohort.isin(earlier)]
    sa, sb = a.act240.mean(), b.act240.mean()
    ya, yb = a.loc[a.act240 == 1, "adopt240"].values, b.loc[b.act240 == 1, "adopt240"].values

    def trim(y, p):
        n = len(y)
        k = int(round(p * n))
        m = y.sum()
        lo = max(m - k, 0) / (n - k)          # remove adopters first
        hi = min(m, n - k) / (n - k)          # remove non-adopters first
        return lo, hi
    if sa >= sb:
        lo_a, hi_a = trim(ya, (sa - sb) / sa)
        mb = yb.mean()
        return lo_a - mb, hi_a - mb, sa, sb
    lo_b, hi_b = trim(yb, (sb - sa) / sb)
    ma = ya.mean()
    return ma - hi_b, ma - lo_b, sa, sb


def lee_all(d):
    ak = lee_pair(d, ["A27"], ["A26"])
    cm = lee_pair(d, ["F34", "C34"], ["F21", "C21"])
    return dict(akka=ak[:2], typelevel=cm[:2], did=(ak[0] - cm[1], ak[1] - cm[0]),
                act_shares=dict(A27=ak[2], A26=ak[3], tl_late=cm[2], tl_early=cm[3]))


L7 = D[D.cohort.isin(["A26", "A27", "F21", "C21", "F34", "C34"])].reset_index(drop=True)
pt = lee_all(L7)
rng = np.random.default_rng(20261112)
owners = L7.owner.unique()
byo = {o: ix for o, ix in L7.groupby("owner").indices.items()}
bs = {"akka": [], "did": []}
for _ in range(2000):
    pick = rng.choice(owners, size=len(owners), replace=True)
    bd = L7.iloc[np.concatenate([byo[o] for o in pick])]
    r = lee_all(bd)
    bs["akka"].append(r["akka"])
    bs["did"].append(r["did"])
E7 = {"point": {k: [round(float(x), 4) for x in v] if isinstance(v, tuple) else {kk: round(float(vv), 4) for kk, vv in v.items()} for k, v in pt.items()}}
for k in ("akka", "did"):
    arr = np.array(bs[k])
    E7[f"ci95_{k}"] = [round(float(np.quantile(arr[:, 0], 0.025)), 4), round(float(np.quantile(arr[:, 1], 0.975)), 4)]
out["E7_lee_bounds"] = E7
print("E7:", E7, flush=True)

# ---- section 4: A24 / E8 ----
a24 = D[D.cohort == "A24"]
out["A24"] = dict(risk_set=int(len(a24)), active240=int(a24.act240.sum()), included=bool(a24.act240.sum() >= 30))
if out["A24"]["included"]:
    s = D[D.cohort.isin(["A24", "A25", "A26", "A27"])].reset_index(drop=True)
    t0 = pd.Timestamp("2015-09-30")
    s["t"] = s.cohort.map(lambda c: (pd.Timestamp(LAUNCH[c]) - t0).days / 365.25)
    s["a27"] = (s.cohort == "A27").astype(int)
    for wt in (True, False):
        tag = "weighted" if wt else "unweighted"
        out["A24"][f"E8_{tag}"] = fit(s, "adopt240", ["t", "a27"], 2, wt, False)[0]
    out["A24"]["adopt240_share"] = round(float(a24.adopt240.mean()), 4)
    out["A24"]["y1_active_share"] = round(float(a24.loc[a24.act240 == 1, "adopt240"].mean()), 4)
    print("E8:", out["A24"], flush=True)

# ---- section 5: activity diagnostics ----
ry = pd.read_csv(LU / "release_years.csv")
cont = []
for src_, g in ry.groupby("source"):
    yrs = g.groupby("project").year.apply(set)
    for y in range(2016, 2026):
        base_ = yrs[yrs.apply(lambda s_: y - 1 in s_)]
        cont.append(dict(source=src_, year=y, base=len(base_), continued=round(float(base_.apply(lambda s_: y in s_).mean()), 4)))
pd.DataFrame(cont).to_csv(O / "activity_continuation.csv", index=False)
aux = pd.read_csv(LU / "aux_preline.csv").merge(D[["cohort", "project", "act240"]], on=["cohort", "project"])
out["B5_preline_by_activity"] = {c: g.groupby(["pre_line", "act240"]).size().unstack(fill_value=0).to_dict(orient="index")
                                 for c, g in aux[aux.cohort.isin(["C21", "F21", "C34", "F34"])].groupby("cohort")}

# ---- section 6: checks behind the paper's claims ----
e1, e3 = out["E_unconditional_h240"]["E1_weighted"], out["E_unconditional_h240"]["E3_weighted"]
excl = lambda r: (r["ci95"][0] > 0 or r["ci95"][1] < 0) and r["p_wcb"] < 0.05
fz, ina = e6["freeze240_E1_weighted"], e6["inactive240_E1_weighted"]
out["claim_checks"] = {
    "headline_E1_E3_exclude_zero": bool(excl(e1) and excl(e3)),
    "freeze_claim_extends_to_cohort": bool(fz["coef"] > ina["coef"] and ina["ci95"][0] <= 0 <= ina["ci95"][1]),
    "freeze_claim_inputs": {"freeze_rise": fz["coef"], "inactive_rise": ina["coef"], "inactive_ci95": ina["ci95"]},
}
(O / "launch_estimates.json").write_text(json.dumps(out, indent=1, default=str))
print(json.dumps(out["claim_checks"], indent=1))
print(shares)
