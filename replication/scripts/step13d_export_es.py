"""Step 13d: export event-study coefficients and owner-clustered covariance for HonestDiD (step13e_honestdid.R).

Same event study as step13b_honest.py (Step 11 section 5.2 specification). Order: pre-period quarters in time order
(reference quarter omitted), then the event quarter and the post-period quarters.
Outputs: outputs/step13/hd_{event}_{outcome}_beta.csv, hd_{event}_{outcome}_sigma.csv, hd_meta.json
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
meta = {}
for ev in ("akka", "es"):
    b = E.weights(PJ, ev)[0]
    for m in ("M1", "M1s"):
        d = PQ[(PQ.event == ev) & PQ.period.isin(["pre", "event", "post"]) & PQ[m].notna()].merge(
            b[["project", "group", "w"]], on=["project", "group"], how="inner").reset_index(drop=True)
        qs = sorted(q for q in d.quarter.unique() if q != REF[ev])
        cols = []
        for q in qs:
            d["Dq_" + q] = d.treated * (d.quarter == q)
            cols.append("Dq_" + q)
        f = E.twfe(d, m, cols, w=d.w)
        per = [d[d.quarter == q].period.iloc[0] for q in qs]
        idx = [i for i, p in enumerate(per) if p == "pre"] + [i for i, p in enumerate(per) if p != "pre"]
        pd.DataFrame({"quarter": [qs[i] for i in idx], "period": [per[i] for i in idx], "beta": f.beta[idx]}).to_csv(
            O / f"hd_{ev}_{m}_beta.csv", index=False)
        np.savetxt(O / f"hd_{ev}_{m}_sigma.csv", f.V[np.ix_(idx, idx)], delimiter=",")
        meta[f"{ev}_{m}"] = dict(n_pre=sum(p == "pre" for p in per), n_post=sum(p != "pre" for p in per),
                                  clusters=int(f.G), n_obs=int(f.n))
(O / "hd_meta.json").write_text(json.dumps(meta, indent=1))
print(json.dumps(meta, indent=1))
