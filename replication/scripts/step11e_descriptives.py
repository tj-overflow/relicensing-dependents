"""Step 11e: descriptive analyses.

1. Decomposition (P4): treated M1 split into raises within the open line and raises into restricted versions,
   by period and by quarter, both events.
2. Unconditional status by calendar quarter-end, with "no release" as a category, both events. Status at a date
   follows the Step 4 (Akka) and Step 8 (Elasticsearch) horizon rules applied to releases up to that date.
3. E1 (Akka): cumulative switch-or-dual share by months since complete port availability, by Step 7 cohort.
4. E4 (Akka): among projects frozen at 2023-06-30, cumulative transitions out of freeze by month, 2023-07..2024-06.
   E5: the same for projects frozen at 2024-09-30, 2024-10..2025-09.
5. E2 (Akka, exploratory): switch-or-dual share 12/24/36 months after Pekko 1.0 by owner type (A1), with bounds
   from the Step 5 confusion matrix; foundation owners separate. Runs only when data/raw/step11/owners.json exists.
6. Elasticsearch reversal window (P8): treated quarterly AGPL uptake, OpenSearch use, M1 and M1_restr, 2023Q4-2025Q3.
Outputs: outputs/step11/descriptives.json, status_quarterly.csv, e1_curves.csv, transitions.csv
"""
import csv
import json
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
O = ROOT / "outputs/step11"
pj = pd.read_csv(O / "projects.csv")
pq = pd.read_csv(O / "panel.csv")
out = {}

# ---------- 1. decomposition ----------
t = pq[(pq.treated == 1) & pq.M1.notna()]
out["decomposition_by_period"] = {
    ev: t[t.event == ev].groupby("period")[["M1", "M1_open", "M1_restr"]].mean().round(3).to_dict(orient="index")
    for ev in ("akka", "es")}
out["decomposition_by_quarter"] = {
    ev: t[t.event == ev].groupby("quarter")[["M1", "M1_open", "M1_restr"]].mean().round(3).to_dict(orient="index")
    for ev in ("akka", "es")}
c = pq[(pq.treated == 0) & pq.M1.notna()]
out["comparison_M1_by_period"] = {ev: c[c.event == ev].groupby("period").M1.mean().round(3).to_dict() for ev in ("akka", "es")}


# ---------- status at a date ----------
def cutoff6(pl):
    y, m = int(pl[:4]), int(pl[5:7])
    return f"{y - (1 if m <= 6 else 0):04d}-{(m - 7) % 12 + 1:02d}{pl[7:10]}"


def akka_status(final):
    if final & {"pekko", "mixed"} and final & {"akka_open", "akka_bsl", "akka_unresolved"}:
        return "dual"
    if final & {"pekko", "mixed"}:
        return "switch"
    if "akka_bsl" in final:
        return "upgrade"
    if final & {"akka_open", "akka_unresolved"}:
        return "freeze"
    return "removed"


ES_ANY = {"es_open", "es_restricted", "es_agpl", "es_unresolved"}


def es_status(ks):
    ks = set(ks)
    if "vendor_new_client" in ks:
        ks.add("vendor_open")
    if "opensearch" in ks and (ks & ES_ANY or "vendor_open" in ks):
        return "dual"
    if "opensearch" in ks:
        return "switch"
    if "es_restricted" in ks:
        return "upgrade"
    if "es_agpl" in ks:
        return "upgrade_agpl"
    if "es_open" in ks:
        return "freeze"
    if "es_unresolved" in ks:
        return "es_version_unresolved"
    if "vendor_open" in ks:
        return "vendor_open"
    if "spring_data" in ks:
        return "spring_only"
    return "removed"


def status_at(rels, event, d, fn):
    """rels: list of (published, package, payload); Step 4/8 horizon rule at date d"""
    post = [x for x in rels if event <= x[0] <= d]
    if not post:
        return "no_release"
    last = {}
    for x in post:
        last[x[1]] = x
    cut = cutoff6(max(x[0] for x in last.values()))
    return fn([x for x in last.values() if x[0] >= cut])


ak_proj = set(pj[(pj.event == "akka") & (pj.treated == 1)].project)
ak_rel = defaultdict(list)
for r in csv.DictReader(open(ROOT / "outputs/step04/project_panel.csv", encoding="utf-8")):
    if r["project"] in ak_proj:
        ak_rel[r["project"]].append((r["published"], r["package"], r["status"]))
for v in ak_rel.values():
    v.sort()
es_proj = set(pj[(pj.event == "es") & (pj.treated == 1)].project)
es_rel = defaultdict(list)
for r in csv.DictReader(open(ROOT / "outputs/step08/es_project_panel.csv", encoding="utf-8")):
    if r["project"] in es_proj:
        es_rel[r["project"]].append((r["published"], r["package"], set(filter(None, r["kinds"].split(";")))))
for v in es_rel.values():
    v.sort()
AK = lambda xs: akka_status({x[2] for x in xs})  # noqa: E731
ESF = lambda xs: es_status(set().union(*[x[2] for x in xs]))  # noqa: E731


def quarter_ends(a, b):
    out, y, q = [], int(a[:4]), (int(a[5:7]) - 1) // 3 + 1
    while True:
        d = f"{y}-{q * 3:02d}-{[31, 30, 30, 31][q - 1]}"
        if d > b:
            return out
        out.append(d)
        y, q = (y + 1, 1) if q == 4 else (y, q + 1)


rows = []
for ev, rels, ev_date, fn, end in (("akka", ak_rel, "2022-09-07", AK, "2025-09-30"), ("es", es_rel, "2021-01-14", ESF, "2025-09-30")):
    projs = ak_proj if ev == "akka" else es_proj
    for d in quarter_ends(ev_date, end):
        cnt = defaultdict(int)
        for p in projs:
            cnt[status_at(rels.get(p, []), ev_date, d, fn)] += 1
        rows.append(dict(event=ev, date=d, n=len(projs), **cnt))
sq = pd.DataFrame(rows).fillna(0)
sq.to_csv(O / "status_quarterly.csv", index=False)
out["status_at_horizon_share"] = {
    ev: (sq[sq.event == ev].iloc[-1].drop(["event", "date", "n"]) / sq[sq.event == ev].iloc[-1]["n"]).astype(float).round(3).to_dict()
    for ev in ("akka", "es")}

# ---------- 3. E1 curves ----------
td = {r["project"]: r for r in csv.DictReader(open(ROOT / "outputs/step07/treatment_dates.csv", encoding="utf-8"))}
v2 = {r["project"]: r for r in csv.DictReader(open(ROOT / "outputs/step05/risk_set_v2.csv", encoding="utf-8"))}


def months(a, b):
    return (int(b[:4]) - int(a[:4])) * 12 + int(b[5:7]) - int(a[5:7])


def cohort(T):
    if not T or T == "n/a" or T > "2025-09-30":
        return "never"
    q = f"{T[:4]}Q{(int(T[5:7]) - 1) // 3 + 1}"
    return q if q in ("2023Q3", "2023Q4") else "2024Q1+"


e1 = []
act = [p for p in ak_proj if v2[p]["active_post"] == "1" and p in td]
# fixed sample per cohort: every project is followed to the cohort's shortest follow-up (no composition change)
kmax = defaultdict(lambda: 10 ** 6)
for p in act:
    co = cohort(td[p]["T_all"])
    if co != "never":
        kmax[co] = min(kmax[co], months(td[p]["T_all"], "2025-09-30"))
for k in range(0, 27):
    by = defaultdict(lambda: [0, 0])
    for p in act:
        T = td[p]["T_all"]
        co = cohort(T)
        if co == "never" or k > kmax[co]:
            continue
        fs = v2[p]["first_switch_v2"]
        by[co][1] += 1
        by[co][0] += int(bool(fs) and months(T, fs) <= k)
    for co, (s, n) in by.items():
        e1.append(dict(months_since_availability=k, cohort=co, n=n, share_switch_or_dual=round(s / n, 3)))
pd.DataFrame(e1).to_csv(O / "e1_curves.csv", index=False)
never = [p for p in act if cohort(td[p]["T_all"]) == "never"]
out["E1"] = dict(active_with_dates=len(act), cohort_sizes=dict(pd.Series([cohort(td[p]["T_all"]) for p in act]).value_counts()),
                 never_available_switch_or_dual=f"{sum(bool(v2[p]['first_switch_v2']) for p in never)}/{len(never)}",
                 at_12_months={r["cohort"]: r["share_switch_or_dual"] for r in e1 if r["months_since_availability"] == 12})


# ---------- 4. E4 / E5 transitions ----------
def month_ends(a, b):
    out, y, m = [], int(a[:4]), int(a[5:7])
    while True:
        d = f"{y}-{m:02d}-{[31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]}"
        if d > b:
            return out
        out.append(d)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


tr = []
for lab, base, a, b in (("E4_end_of_patches", "2023-06-30", "2023-07-01", "2024-06-30"),
                        ("E5_licence_keys", "2024-09-30", "2024-10-01", "2025-09-30")):
    frozen = [p for p in ak_proj if status_at(ak_rel.get(p, []), "2022-09-07", base, AK) == "freeze"]
    left = {}
    for d in month_ends(a, b):
        cnt = defaultdict(int)
        for p in frozen:
            if p in left:
                cnt[left[p]] += 1
                continue
            s = status_at(ak_rel.get(p, []), "2022-09-07", d, AK)
            if s in ("switch", "dual", "upgrade", "removed"):
                left[p] = s
                cnt[s] += 1
        tr.append(dict(window=lab, month_end=d, frozen_at_base=len(frozen), **{f"cum_{k}": v for k, v in cnt.items()}))
    out[lab] = dict(frozen_at_base=len(frozen), left_by_end={k: v for k, v in pd.Series(left).value_counts().items()})
pd.DataFrame(tr).fillna(0).to_csv(O / "transitions.csv", index=False)

# ---------- 5. E2 by owner type ----------
own_f = ROOT / "data/raw/step11/owners.json"
if own_f.exists():
    owners = {k.lower(): v for k, v in json.loads(own_f.read_text(encoding="utf-8")).items()}
    e2 = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for p in act:
        r = v2[p]
        o = p.split("/")[1].lower() if p.startswith("github.com/") else ""
        typ = "foundation" if r["foundation"] else {"Organization": "A1=1", "User": "A1=0"}.get(owners.get(o, {}).get("type"), "unknown")
        for k in (12, 24, 36):
            d_end = f"{2023 + (6 + k) // 12:04d}-{(6 + k) % 12 + 1:02d}-10"
            if d_end > "2025-09-30":
                continue
            fs = r["first_switch_v2"]
            e2[f"{k}m"][typ][1] += 1
            e2[f"{k}m"][typ][0] += int(bool(fs) and fs <= d_end)
    res = {}
    for k, by in e2.items():
        res[k] = {t: dict(n=n, share=round(s / n, 3)) for t, (s, n) in by.items()}
        a1, a0 = by.get("A1=1", [0, 0]), by.get("A1=0", [0, 0])
        if a1[1] and a0[1]:
            res[k]["difference_A1"] = round(a1[0] / a1[1] - a0[0] / a0[1], 3)
    # bounds: Step 5 found 12 of the A1=1 projects (of 58) were non-commercial organizations and no false negatives;
    # PPV of A1 = (n_A1 - 12) / n_A1 in that sample. The exposed-minus-unexposed difference is attenuated by
    # misclassification of A1=1 projects only; a simple bound rescales the difference by 1/PPV.
    res["note_bounds"] = "Step 5: 12 false positives, 0 false negatives among 58; the A1 difference is attenuated toward zero by false positives. Upper bound on |difference| = |difference| / PPV."
    out["E2"] = res
else:
    out["E2"] = "owner types not yet collected"

# ---------- 6. Elasticsearch reversal ----------
r = pq[(pq.event == "es") & (pq.treated == 1) & pq.quarter.between("2023Q4", "2025Q3")]
out["es_reversal"] = r.groupby("quarter").agg(n=("project", "size"), any_agpl=("any_agpl", "mean"), any_os=("any_fork", "mean"),
                                              M1=("M1", "mean"), M1_restr=("M1_restr", "mean")).round(3).to_dict(orient="index")
(O / "descriptives.json").write_text(json.dumps(out, indent=1, default=str))
print(json.dumps({k: v for k, v in out.items() if k != "decomposition_by_quarter"}, indent=1, default=str))
