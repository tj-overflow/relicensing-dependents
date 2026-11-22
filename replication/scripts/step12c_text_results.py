"""Step 12c: motive shares from coder A (project level), agreement with coder B, validation sample.

Inputs: outputs/step12/text_coded_projects.csv (coder A, the model in this session, project level, from
text_for_coding_projects.txt), text_project_items.csv + text_keyword.csv (coder B, keyword rule, aggregated to
the project over the same selected items: a flag is 1 if any selected item has it).
Deviations from the codebook (recorded in the Step 12 note): project-level unit; two codes added while coding,
LICENCE_UNSPEC (the licence change is given as the reason without saying how it binds) and USER_REQUEST (a user
asked for the fork, motive not stated). Vendor projects (lagom) are excluded from shares.
Outputs: outputs/step12/text_results.json, text_validation_sample.csv
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import fisher_exact

ROOT = Path(__file__).resolve().parents[1]
O = ROOT / "outputs/step12"
A = pd.read_csv(O / "text_coded_projects.csv", keep_default_na=False)
A = A[~A.repo.eq("lagom/lagom")]
CODES = ["LEGAL_OWN", "LEGAL_USERS", "LICENCE_UNSPEC", "USER_REQUEST", "TRUST", "AGEING", "COMPAT", "COORD", "COST"]
for c in CODES:
    A[c] = A.codes.str.split(";").apply(lambda xs: int(c in xs))
A["LEGAL_ANY"] = (A.LEGAL_OWN | A.LEGAL_USERS).astype(int)
A["LICENCE_ANY"] = (A.LEGAL_ANY | A.LICENCE_UNSPEC).astype(int)
A["ANY_MOTIVE"] = (A[CODES].drop(columns=["USER_REQUEST"]).sum(axis=1) > 0).astype(int)
R = A[A.R == 1]
res = {"repositories_coded": A.groupby("event").size().to_dict(),
       "relevant": R.groupby("event").size().to_dict()}
sh = {}
for ev, g in R.groupby("event"):
    n = len(g)
    sh[ev] = {c: dict(n=int(g[c].sum()), share=round(g[c].mean(), 3))
              for c in CODES + ["LEGAL_ANY", "LICENCE_ANY", "ANY_MOTIVE"]}
    sh[ev]["n_relevant"] = n
    sh[ev]["actions"] = g.action.value_counts().to_dict()
res["shares_among_relevant"] = sh
ak, es = R[R.event == "akka"], R[R.event == "es"]
tests = {}
for c in ["LEGAL_ANY", "LICENCE_ANY", "COMPAT", "TRUST", "USER_REQUEST"]:
    t = [[int(ak[c].sum()), int(len(ak) - ak[c].sum())], [int(es[c].sum()), int(len(es) - es[c].sum())]]
    tests[c] = dict(akka=t[0], es=t[1], fisher_p=round(float(fisher_exact(t)[1]), 4))
res["akka_vs_es"] = tests
# among projects that state any motive
for ev, g in R[R.ANY_MOTIVE == 1].groupby("event"):
    res.setdefault("shares_among_stated_motive", {})[ev] = dict(
        n=len(g), **{c: round(g[c].mean(), 3) for c in ["LICENCE_ANY", "LEGAL_ANY", "TRUST", "COMPAT", "AGEING", "COORD", "COST"]})

# coder B agreement at the project level
it = pd.read_csv(O / "text_project_items.csv")
kw = pd.read_csv(O / "text_keyword.csv")
B = it[["id", "event", "repo"]].merge(kw, on="id").groupby(["event", "repo"]).max(numeric_only=True).reset_index()
M = A.merge(B, on=["event", "repo"], suffixes=("_A", "_B"))


def kappa(x, y):
    x, y = np.asarray(x), np.asarray(y)
    po = (x == y).mean()
    pe = x.mean() * y.mean() + (1 - x.mean()) * (1 - y.mean())
    return None if pe == 1 else round(float((po - pe) / (1 - pe)), 3)


agr = {"R": dict(kappa=kappa(M.R, M.R_kw), A=int(M.R.sum()), B=int(M.R_kw.sum()), n=len(M))}
Mr = M[M.R == 1]
for c in ["LEGAL_OWN", "LEGAL_USERS", "TRUST", "AGEING", "COMPAT", "COORD", "COST"]:
    agr[c] = dict(kappa=kappa(Mr[c + "_A"], Mr[c + "_B"]), A=int(Mr[c + "_A"].sum()), B=int(Mr[c + "_B"].sum()))
agr["LICENCE_ANY_vs_B_LEGAL_OWN"] = dict(kappa=kappa(Mr.LICENCE_ANY, Mr.LEGAL_OWN_B),
                                         A=int(Mr.LICENCE_ANY.sum()), B=int(Mr.LEGAL_OWN_B.sum()))
res["agreement_A_vs_B_project_level"] = agr

# validation sample for a human coder: 30 repositories per event, all LEGAL/TRUST-coded ones first, then random
rng = np.random.default_rng(20261110)
rows = []
for ev, g in A.groupby("event"):
    pri = g[(g.LEGAL_ANY == 1) | (g.TRUST == 1)]
    rest = g.drop(pri.index)
    k = max(0, 30 - len(pri))
    pick = pd.concat([pri, rest.iloc[rng.permutation(len(rest))[:k]]])
    rows.append(pick[["event", "repo"]])
vs = pd.concat(rows).merge(it[["event", "repo", "id", "number", "title"]], on=["event", "repo"])
for c in ["R"] + CODES + ["action"]:
    vs["human_" + c] = ""
vs.to_csv(O / "text_validation_sample.csv", index=False)
res["validation_sample"] = dict(repositories=int(vs[["event", "repo"]].drop_duplicates().shape[0]), items=len(vs))
(O / "text_results.json").write_text(json.dumps(res, indent=1))
print(json.dumps(res, indent=1))
