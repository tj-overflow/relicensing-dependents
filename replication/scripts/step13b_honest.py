"""Step 13b: sensitivity to parallel trends, Python implementation.

A Python implementation of the relative-magnitudes bound, kept as a cross-check of step13e_honestdid.R.
This script implements:
  Event study as in Step 11 (section 5.2), re-estimated here to keep the full owner-clustered covariance.
  Relative magnitudes, Delta^RM(Mbar): every post-period first difference of the bias delta is at most Mbar times
    the largest pre-period first difference (reference quarter delta = 0; the event quarter is post period 1).
    For a target theta = l'tau_post with l >= 0, the identified set is closed form (it is the LP solution):
      l'b_post -/+ Mbar * m * sum_t l_t * t,   m = max_s |b_s - b_{s-1}| over the pre-period.
    The confidence set is approximate: 20,000 draws b* ~ N(b, V); CI = [q2.5(lower*), q97.5(upper*)]. This is not
    the ARP conditional / hybrid interval HonestDiD reports, and the HonestDiD numbers should replace it.
  Smoothness, Delta^SD(0): delta linear through the pre-period and the reference quarter. theta is
    l'(b_post - s*t), with s the GLS slope of the pre-period coefficients through the origin; CI from the delta
    method with the full covariance. Delta^SD(M > 0) is left to HonestDiD (FLCI).
Targets (the first is the analogue of beta):
  avg_post: mean over all post quarters after the event quarter;
  first_year: mean over the first four post quarters after the event quarter.
Outcomes: M1 (primary), M1s (calendar-adjusted), both events.
Outputs: outputs/step13/honest.json, event_study_full.csv
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import step11_est as E  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
O = ROOT / "outputs/step13"
PJ = pd.read_csv(ROOT / "outputs/step11/projects.csv")
PQ = pd.read_csv(ROOT / "outputs/step11/panel.csv")
REF = {"akka": "2022Q2", "es": "2020Q4"}
MBARS = [0.1, 0.25, 0.5, 1.0, 1.5, 2.0]
rng = np.random.default_rng(20261110)


def event_study(ev, m):
    b = E.weights(PJ, ev)[0]
    d = PQ[(PQ.event == ev) & PQ.period.isin(["pre", "event", "post"]) & PQ[m].notna()].merge(
        b[["project", "group", "w"]], on=["project", "group"], how="inner").reset_index(drop=True)
    qs = sorted(q for q in d.quarter.unique() if q != REF[ev])
    cols = []
    for q in qs:
        c = "Dq_" + q
        d[c] = d.treated * (d.quarter == q)
        cols.append(c)
    f = E.twfe(d, m, cols, w=d.w)
    per = [d[d.quarter == q].period.iloc[0] for q in qs]
    pre = [i for i, p in enumerate(per) if p == "pre"]
    post = [i for i, p in enumerate(per) if p != "pre"]  # event quarter first
    return qs, per, f.beta, f.V, pre, post, f


def rm_bounds(bpre, bpost, l, mbar):
    path = np.append(bpre, 0.0)  # pre-period coefficients in time order, then the reference quarter
    mx = np.max(np.abs(np.diff(path)))
    t = np.arange(1, len(bpost) + 1)
    c = float(l @ t)
    th = float(l @ bpost)
    return th - mbar * mx * c, th + mbar * mx * c, mx


def sd0(bpre, bpost, Vpre, Vall, pre, post, l):
    tp = -np.arange(len(bpre), 0, -1, dtype=float)  # pre quarters at -k..-1 relative to the reference (0)
    Vi = np.linalg.inv(Vpre)
    s = float(tp @ Vi @ bpre) / float(tp @ Vi @ tp)
    t = np.arange(1, len(bpost) + 1, dtype=float)
    th = float(l @ bpost) - s * float(l @ t)
    # gradient of theta wrt (b_pre, b_post)
    gs = (Vi @ tp) / float(tp @ Vi @ tp)
    g = np.zeros(len(pre) + len(post))
    g[:len(pre)] = -float(l @ t) * gs
    g[len(pre):] = l
    se = float(np.sqrt(g @ Vall @ g))
    return th, se, s


out, es_rows = {}, []
for ev in ("akka", "es"):
    for m in ("M1", "M1s"):
        qs, per, b, V, pre, post, f = event_study(ev, m)
        F, p = E.wald(f, pre)
        for i, q in enumerate(qs):
            es_rows.append(dict(event=ev, outcome=m, quarter=q, period=per[i], coef=b[i], se=np.sqrt(V[i, i])))
        es_rows.append(dict(event=ev, outcome=m, quarter=REF[ev], period="pre", coef=0.0, se=0.0))
        idx = pre + post
        bb, VV = b[idx], V[np.ix_(idx, idx)]
        npre, npost = len(pre), len(post)
        targets = {"avg_post": np.r_[0.0, np.full(npost - 1, 1 / (npost - 1))],
                   "first_year": np.r_[0.0, np.full(4, 0.25), np.zeros(npost - 5)]}
        draws = rng.multivariate_normal(bb, VV, size=20000)
        res = dict(joint_pre_F=round(F, 3), joint_pre_p=round(p, 4), n_pre=npre, n_post_incl_event_quarter=npost)
        for tname, l in targets.items():
            th = float(l @ bb[npre:])
            se = float(np.sqrt(l @ VV[npre:, npre:] @ l))
            r = dict(theta=round(th, 4), se=round(se, 4), ci95_parallel_trends=[round(th - 1.96 * se, 4), round(th + 1.96 * se, 4)])
            lo0, hi0, mx = rm_bounds(bb[:npre], bb[npre:], l, 0)
            r["max_pre_first_difference"] = round(mx, 4)
            rm = {}
            for mb in MBARS:
                lo, hi, _ = rm_bounds(bb[:npre], bb[npre:], l, mb)
                L = np.array([rm_bounds(x[:npre], x[npre:], l, mb)[0] for x in draws])
                U = np.array([rm_bounds(x[:npre], x[npre:], l, mb)[1] for x in draws])
                rm[str(mb)] = dict(identified_set=[round(lo, 4), round(hi, 4)],
                                   ci95_approx=[round(float(np.quantile(L, 0.025)), 4), round(float(np.quantile(U, 0.975)), 4)])
            r["relative_magnitudes"] = rm
            # breakdown: smallest Mbar on a 0.01 grid at which the approximate CI contains zero
            mxd = np.array([np.max(np.abs(np.diff(np.append(x[:npre], 0.0)))) for x in draws])
            thd = draws[:, npre:] @ l
            c = float(l @ np.arange(1, npost + 1))
            bd = None
            for mb in np.arange(0, 3.001, 0.01):
                if np.quantile(thd - mb * mxd * c, 0.025) <= 0 <= np.quantile(thd + mb * mxd * c, 0.975):
                    bd = round(float(mb), 2)
                    break
            r["breakdown_Mbar_approx"] = bd
            r["breakdown_Mbar_identified_set"] = round(abs(th) / (mx * c), 3) if mx > 0 else None
            th0, se0, s = sd0(bb[:npre], bb[npre:], VV[:npre, :npre], VV, pre, post, l)
            r["smoothness_M0_linear_extrapolation"] = dict(theta=round(th0, 4), se=round(se0, 4),
                                                           ci95=[round(th0 - 1.96 * se0, 4), round(th0 + 1.96 * se0, 4)],
                                                           pre_slope_per_quarter=round(s, 4))
            res[tname] = r
        out[f"{ev} {m}"] = res
        print(ev, m, json.dumps({k: (v if not isinstance(v, dict) else {a: v[a] for a in ("theta", "ci95_parallel_trends", "max_pre_first_difference", "breakdown_Mbar_approx", "breakdown_Mbar_identified_set", "smoothness_M0_linear_extrapolation")}) for k, v in res.items()}), flush=True)

# cross-event difference of the average post effect under RM (identified sets combined at the extremes)
for m in ("M1", "M1s"):
    a, e = out[f"akka {m}"]["avg_post"], out[f"es {m}"]["avg_post"]
    out[f"delta {m} avg_post"] = {mb: dict(identified_set=[round(a["relative_magnitudes"][mb]["identified_set"][0] - e["relative_magnitudes"][mb]["identified_set"][1], 4),
                                                           round(a["relative_magnitudes"][mb]["identified_set"][1] - e["relative_magnitudes"][mb]["identified_set"][0], 4)])
                                  for mb in a["relative_magnitudes"]}
pd.DataFrame(es_rows).sort_values(["event", "outcome", "quarter"]).to_csv(O / "event_study_full.csv", index=False)
(O / "honest.json").write_text(json.dumps(out, indent=1))
