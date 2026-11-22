"""Step 13c: inference for the foundation interaction (exploratory, added after Step 12).

The owner-clustered SE of D x foundation rests on two treated foundation owners in Elasticsearch (apache, eclipse),
so it is not credible. Two alternatives:
  project-clustered SE;
  randomization inference: the foundation label is reassigned at random among treated projects, keeping the
  number of labelled projects with and without both pre- and post-period quarters (only the former identify the
  interaction under project FE),
  2,000 draws, seed 20261110; p = share of |coef*| >= |coef|.
Output: outputs/step13/foundation.json
"""
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import step11_est as E  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PJ = pd.read_csv(ROOT / "outputs/step11/projects.csv")
PQ = pd.read_csv(ROOT / "outputs/step11/panel.csv")
FOUND = re.compile(r"^(apache|eclipse.*|jakartaee|finos)$")
rng = np.random.default_rng(20261110)
out = {}
for ev in ("es", "akka"):
    b = E.weights(PJ, ev)[0]
    d = PQ[(PQ.event == ev) & PQ.period.isin(["pre", "post"]) & PQ.M1.notna()].merge(
        b[["project", "group", "w"]], on=["project", "group"], how="inner").reset_index(drop=True)
    d["D"] = d.treated * (d.period == "post")
    d["F"] = d.owner.str.lower().str.match(FOUND).astype(int)
    d["DF"] = d.D * d.F
    f = E.twfe(d, "M1", ["D", "DF"], w=d.w)
    fp = E.twfe(d, "M1", ["D", "DF"], w=d.w, cluster="project")
    both = d[d.treated == 1].groupby("project").period.agg(lambda x: {"pre", "post"} <= set(x))
    tr_post = both[both].index.values
    tr_nopost = np.setdiff1d(d[d.treated == 1].project.unique(), tr_post)
    lab = set(d[(d.treated == 1) & (d.F == 1)].project)
    k = len(lab)
    k_post = len(lab & set(tr_post))
    draws = []
    for _ in range(2000):
        pick = set(rng.choice(tr_post, size=k_post, replace=False)) | set(rng.choice(tr_nopost, size=k - k_post, replace=False))
        x = d.copy()
        x["DF"] = x.D * x.project.isin(pick)
        draws.append(float(E.twfe(x, "M1", ["D", "DF"], w=x.w).beta[1]))
    draws = np.array(draws)
    c = float(f.beta[1])
    out[ev] = dict(coef_DF=round(c, 4), se_owner=round(float(f.se[1]), 4), se_project=round(float(fp.se[1]), 4),
                   coef_D_nonfoundation=round(float(f.beta[0]), 4), treated_foundation_projects=k,
                   treated_foundation_owners=sorted(d[(d.treated == 1) & (d.F == 1)].owner.str.lower().unique().tolist()),
                   foundation_projects_identifying=k_post,
                   p_ri=round(float(np.mean(np.abs(draws) >= abs(c))), 4), ri_sd=round(float(draws.std()), 4))
    print(ev, out[ev], flush=True)
(ROOT / "outputs/step13/foundation.json").write_text(json.dumps(out, indent=1))
