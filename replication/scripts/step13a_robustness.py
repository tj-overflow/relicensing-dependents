"""Step 13a: robustness of the section 5.1 estimates, both events.

Every row is the 5.1 specification (project and quarter FE, ATT weights, owner clusters, pre and post periods,
event quarter excluded) with one change:
  1  M1c, M1s in place of M1
  2  M3 in place of M1
  3  unweighted; no project FE (group FE instead, the Step 6 form)
  4  line-specific comparison: Akka vs cats-effect; ES embedded vs Lucene; ES client vs SolrJ
     (Step 11 weights kept for the subset)
  5  excluding the top 3 owners by risk-set project count in each group
  6  placebo event date in the pre-period (Akka 2021Q3, ES 2020Q1), pre-period sample only, placebo quarter excluded
  7  placebo libraries: within the comparison group, each library in turn treated against the others, actual event
     date, unweighted (no propensity model exists for this split)
  8  Akka post-period ending 2024Q3
  9  ES strict codebook: provided scope not declared (panel from step13z_panel_strict.py)
Also the selection check (5.3, balanced non-switchers) for rows 1, 3 and 9.
Added after Step 12 (exploratory, labelled): foundation-governed dependents (owner apache, eclipse*, finos,
jakartaee) interacted with D. Model reading: for these, any non-OSI licence binds, so ELv2
should act on them like BSL.
Added (labelled): treated-specific linear trend estimated on the pre-period and extrapolated,
as a simple companion to the Rambachan-Roth smoothness bound.
Outputs: outputs/step13/robustness.json, robustness_table.csv
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
O = ROOT / "outputs/step13"
O.mkdir(parents=True, exist_ok=True)
PJ = pd.read_csv(ROOT / "outputs/step11/projects.csv")
PQ = pd.read_csv(ROOT / "outputs/step11/panel.csv")
SJ = pd.read_csv(O / "strict/projects.csv")
SQ = pd.read_csv(O / "strict/panel.csv")
FOUND = re.compile(r"^(apache|eclipse.*|jakartaee|finos)$")
QORD = {q: i for i, q in enumerate(sorted(set(PQ.quarter)))}
W = {ev: E.weights(PJ, ev)[0] for ev in ("akka", "es")}
WS = E.weights(SJ, "es")[0]


def sample(ev, m, periods=("pre", "post"), pq=PQ, b=None):
    b = W[ev] if b is None else b
    d = pq[(pq.event == ev) & pq.period.isin(periods) & pq[m].notna()].merge(
        b[["project", "group", "w", "switcher", "tracked"] + (["stratum"] if ev == "es" else [])],
        on=["project", "group", "tracked"] if "tracked" in pq.columns else ["project", "group"], how="inner")
    d["D"] = d.treated * (d.period == "post")
    return d.reset_index(drop=True)


def balanced(d):
    keep = d.groupby("project").period.agg(lambda s: {"pre", "post"} <= set(s))
    d = d[d.project.isin(keep[keep].index)]
    return d[(d.treated == 0) | (d.switcher == 0)].reset_index(drop=True)


def est(d, m="M1", w=True, fe=("project", "quarter"), x=("D",), name="D"):
    f = E.twfe(d, m, list(x), w=d.w if w else None, fe=fe)
    return E.summary(f, name, dict(n_treated=int(d[d.treated == 1].project.nunique()),
                                   n_cmp=int(d[d.treated == 0].project.nunique())))


rows, res = [], {}


def add(item, ev, label, r):
    res[f"{item} | {ev} | {label}"] = r
    rows.append(dict(item=item, event=ev, spec=label, coef=r["coef"], se=r["se"], ci_lo=r["ci95"][0], ci_hi=r["ci95"][1],
                     p=r["p"], n_obs=r["n_obs"], clusters=r["n_clusters"], n_treated=r.get("n_treated"),
                     n_cmp=r.get("n_cmp")))


for ev in ("akka", "es"):
    d = sample(ev, "M1")
    add("0 primary", ev, "M1 (Step 11)", est(d))
    add("0 primary", ev, "M1 balanced non-switchers (Step 11)", est(balanced(d)))
    for m in ("M1c", "M1s"):
        dm = sample(ev, m)
        add("1 outcome", ev, m, est(dm, m))
        add("1 outcome", ev, m + " balanced non-switchers", est(balanced(dm), m))
    add("2 outcome", ev, "M3", est(sample(ev, "M3"), "M3"))
    add("3 form", ev, "unweighted", est(d, w=False))
    add("3 form", ev, "unweighted, balanced non-switchers", est(balanced(d), w=False))
    add("3 form", ev, "no project FE (group FE)", est(d, fe=("group", "quarter")))
    add("3 form", ev, "no project FE, unweighted", est(d, w=False, fe=("group", "quarter")))
    # 4 line-specific
    if ev == "akka":
        add("4 line", ev, "vs cats-effect only", est(d[(d.treated == 1) | (d.tracked == "cats_effect")].reset_index(drop=True)))
    else:
        emb = d[((d.treated == 1) & (d.stratum == "embedded")) | (d.tracked == "lucene")].reset_index(drop=True)
        cli = d[((d.treated == 1) & (d.stratum == "client")) | (d.tracked == "solrj")].reset_index(drop=True)
        add("4 line", ev, "embedded vs Lucene", est(emb))
        add("4 line", ev, "client vs SolrJ", est(cli))
    # 5 top owners
    p = PJ[PJ.event == ev]
    top = []
    for g, x in p.groupby("treated"):
        top += x.owner.value_counts().head(3).index.tolist()
    r = est(d[~d.owner.isin(top)].reset_index(drop=True))
    r["owners_excluded"] = top
    add("5 top owners", ev, "excluding top 3 owners per group", r)
    # 6 placebo date
    pq_ = {"akka": "2021Q3", "es": "2020Q1"}[ev]
    dp = sample(ev, "M1", periods=("pre",))
    dp = dp[dp.quarter != pq_].reset_index(drop=True)
    dp["D"] = dp.treated * (dp.quarter > pq_)
    add("6 placebo date", ev, f"placebo {pq_}, pre-period only", est(dp))
    # 7 placebo libraries
    dc = PQ[(PQ.event == ev) & (PQ.treated == 0) & PQ.period.isin(["pre", "post"]) & PQ.M1.notna()].copy()
    for lib in sorted(dc.tracked.unique()):
        x = dc.copy()
        x["treated"] = (x.tracked == lib).astype(int)
        x["D"] = x.treated * (x.period == "post")
        x["w"] = 1.0
        x = x.reset_index(drop=True)
        if x[x.treated == 1].project.nunique() >= 10:
            add("7 placebo library", ev, f"{lib} vs other comparison libraries", est(x, w=False))
    # foundation exposure (exploratory)
    d["F"] = d.owner.str.lower().str.match(FOUND).astype(int)
    d["DF"] = d.D * d.F
    f = E.twfe(d, "M1", ["D", "DF"], w=d.w)
    rr = E.summary(f, "DF", dict(n_found_treated=int(d[(d.treated == 1) & (d.F == 1)].project.nunique()),
                                 n_found_treated_post=int(d[(d.D == 1) & (d.F == 1)].project.nunique()),
                                 D_nonfoundation=E.summary(f, "D")))
    add("X foundation (exploratory)", ev, "D x foundation owner", rr)
    # treated-specific linear trend (pre-period slope, extrapolated)
    d["tq"] = d.quarter.map(QORD)
    d["Tt"] = d.treated * (d.tq - d[d.period == "pre"].tq.max())
    add("X linear trend (added)", ev, "with treated-specific linear trend", est(d, x=("D", "Tt")))

# 8 Akka window to 2024Q3
d = sample("akka", "M1")
d8 = d[d.quarter <= "2024Q3"].reset_index(drop=True)
add("8 window", "akka", "post-period to 2024Q3", est(d8))
add("8 window", "akka", "post-period to 2024Q3, balanced non-switchers", est(balanced(d8)))
# 9 ES strict codebook
ds = sample("es", "M1", pq=SQ, b=WS)
add("9 strict codebook", "es", "provided scope not declared", est(ds))
add("9 strict codebook", "es", "provided scope not declared, balanced non-switchers", est(balanced(ds)))

pd.DataFrame(rows).to_csv(O / "robustness_table.csv", index=False)
(O / "robustness.json").write_text(json.dumps(res, indent=1))
print(pd.DataFrame(rows)[["item", "event", "spec", "coef", "se", "ci_lo", "ci_hi", "p", "n_treated", "n_cmp"]].to_string())
