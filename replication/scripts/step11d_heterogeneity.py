"""Step 11d: heterogeneity of the primary panel estimate.

Each dimension s: Y = project FE + quarter FE + b0*Treated*Post + b1*Treated*Post*s (s defined for treated projects,
0 for comparison projects), ATT weights, owner clusters, primary sample. Reported: effect for s=0 (b0), for s=1
(b0+b1) and the difference b1, with Benjamini-Hochberg q-values over the family of b1.
  1 scala3_pre_event   2 play_user_pre   3 http_user   4 A1 (owner type Organization; foundation and unknown
  owners excluded from this model)   5 provided_only
A1 bound: Step 5 found 12 false positives and 0 false negatives among the hand-coded A1=1 projects (PPV 20/32);
false positives attenuate b1, so |b1|/PPV bounds its magnitude.
Elasticsearch: the four strata are in step11b (section 5.4).
Output: outputs/step11/heterogeneity.json
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
import step11_est as E  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
O = ROOT / "outputs/step11"
pj = pd.read_csv(O / "projects.csv")
pq = pd.read_csv(O / "panel.csv")
owners = {k.lower(): v for k, v in json.loads((ROOT / "data/raw/step11/owners.json").read_text(encoding="utf-8")).items()}
PPV = 20 / 32

b, _ = E.weights(pj, "akka")
t = b.treated == 1
b["A1"] = np.nan
typ = b.owner.str.lower().map(lambda o: owners.get(o, {}).get("type"))
b.loc[t & (b.foundation.fillna("") == "") & (typ == "Organization"), "A1"] = 1
b.loc[t & (b.foundation.fillna("") == "") & (typ == "User"), "A1"] = 0
b.loc[~t, "A1"] = 0
d0 = pq[(pq.event == "akka") & pq.period.isin(["pre", "post"]) & pq.M1.notna()].merge(
    b[["project", "group", "w", "scala3_pre_event", "play_user_pre", "http_user", "provided_only", "A1"]],
    on=["project", "group"], how="inner")
d0["D"] = d0.treated * (d0.period == "post")
res, pvals = {}, []
for s in ("scala3_pre_event", "play_user_pre", "http_user", "A1", "provided_only"):
    d = d0[d0[s].notna()].copy()
    d["Ds"] = d.D * d[s]
    f = E.twfe(d, "M1", ["D", "Ds"], w=d.w)
    tq = stats.t.ppf(0.975, f.G - 1)
    b0, b1 = f.beta
    se_sum = float(np.sqrt(f.V[0, 0] + f.V[1, 1] + 2 * f.V[0, 1]))
    p1 = float(2 * stats.t.sf(abs(b1 / f.se[1]), f.G - 1))
    pvals.append(p1)
    tr = d[d.treated == 1].drop_duplicates("project")
    r = dict(n_treated_s1=int(tr[s].sum()), n_treated_s0=int((tr[s] == 0).sum()),
             effect_s0=dict(coef=round(b0, 4), se=round(float(f.se[0]), 4)),
             effect_s1=dict(coef=round(b0 + b1, 4), se=round(se_sum, 4)),
             difference=dict(coef=round(b1, 4), se=round(float(f.se[1]), 4),
                             ci95=[round(b1 - tq * f.se[1], 4), round(b1 + tq * f.se[1], 4)], p=round(p1, 4)))
    if s == "A1":
        r["difference"]["bound_abs_over_PPV"] = round(abs(b1) / PPV, 4)
        r["excluded_treated_foundation_or_unknown"] = int(b[t & b.A1.isna()].shape[0])
    res[s] = r
m = len(pvals)
order = np.argsort(pvals)
q = np.empty(m)
prev = 1.0
for rank, i in reversed(list(enumerate(order, 1))):
    prev = min(prev, pvals[i] * m / rank)
    q[i] = prev
for (s, r), qq in zip(res.items(), q):
    r["difference"]["q_bh"] = round(float(qq), 4)
(O / "heterogeneity.json").write_text(json.dumps(res, indent=1))
print(json.dumps(res, indent=1))
