"""Step 12a: mechanism tests from the existing release tables (Akka treated projects, non-vendor risk set).

All descriptive; status rules are the Step 4 horizon rule used in step11e (latest release per artifact within
six months of the project's latest release, up to the date).

A. Exit from BSL around licence keys (Oct 2024). Projects whose status is "upgrade" (on BSL) at 2024-09-30,
   followed to 2025-09-30; placebo window: projects on BSL at 2023-09-30, followed to 2024-09-30.
   Legal channel: keys raise the compliance cost c of staying on the restricted line, so exits to Pekko or back to
   the open line should rise after October 2024 relative to the placebo window.
B. Reversions at the artifact level: a release that declares only the open line (or Pekko) after an earlier
   release of the same artifact declared a BSL version, with a higher artifact version number (a same-day lower
   version is a parallel maintenance branch, not a reversion). Accepting a downgrade gives up g(t); under the model only
   the legal or hold-up term can make it worth it.
C. End of 2.6 patches (P6) by port availability: projects frozen at 2023-06-30, split by whether all their Akka
   dependencies had a Pekko port by 2023-09-30 (Step 7 T_all). Destinations by 2024-06-30.
   If the legal term binds, projects without ports should still not upgrade (they stay frozen or switch late);
   if it is small, they should upgrade.
Output: outputs/step12/mechanisms.json, reversions.csv
"""
import csv
import json
import re
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
O = ROOT / "outputs/step12"
O.mkdir(parents=True, exist_ok=True)
EV = "2022-09-07"
pj = pd.read_csv(ROOT / "outputs/step11/projects.csv")
ak = set(pj[(pj.event == "akka") & (pj.treated == 1)].project)
rels = defaultdict(list)
for r in csv.DictReader(open(ROOT / "outputs/step04/project_panel.csv", encoding="utf-8")):
    if r["project"] in ak:
        rels[r["project"]].append((r["published"], r["package"], r["status"], r["version"]))
for v in rels.values():
    v.sort()


def cutoff6(pl):
    y, m = int(pl[:4]), int(pl[5:7])
    return f"{y - (1 if m <= 6 else 0):04d}-{(m - 7) % 12 + 1:02d}{pl[7:10]}"


def status(final):
    if final & {"pekko", "mixed"} and final & {"akka_open", "akka_bsl", "akka_unresolved"}:
        return "dual"
    if final & {"pekko", "mixed"}:
        return "switch"
    if "akka_bsl" in final:
        return "upgrade"
    if final & {"akka_open", "akka_unresolved"}:
        return "freeze"
    return "removed"


def status_at(p, d):
    post = [x for x in rels.get(p, []) if EV <= x[0] <= d]
    if not post:
        return "no_release"
    last = {}
    for x in post:
        last[x[1]] = x
    cut = cutoff6(max(x[0] for x in last.values()))
    return status({x[2] for x in last.values() if x[0] >= cut})


def vt(v):
    return tuple(int(x) for x in re.findall(r"\d+", str(v))[:4])


out = {}


# ---------- A. exit from BSL ----------
def follow(base, end, start_status):
    base_set = [p for p in ak if status_at(p, base) == start_status]
    dest = defaultdict(int)
    for p in base_set:
        dest[status_at(p, end)] += 1
    return dict(n=len(base_set), status_at_end=dict(dest))


out["A_exit_from_bsl"] = {
    "keys_window_2024-09_to_2025-09": follow("2024-09-30", "2025-09-30", "upgrade"),
    "placebo_window_2023-09_to_2024-09": follow("2023-09-30", "2024-09-30", "upgrade"),
    "frozen_keys_window_for_reference": follow("2024-09-30", "2025-09-30", "freeze"),
    "frozen_placebo_window_for_reference": follow("2023-09-30", "2024-09-30", "freeze"),
}

# ---------- B. reversions ----------
rev = []
first_bsl = {}
for p, xs in rels.items():
    seen_bsl = {}
    for pub, pkg, st, ver in xs:
        if pub < EV:
            continue
        if st == "akka_bsl":
            seen_bsl.setdefault(pkg, (pub, ver))
            first_bsl.setdefault(p, pub)
        elif pkg in seen_bsl and st in ("akka_open", "pekko", "mixed", "none") and vt(ver) > vt(seen_bsl[pkg][1]):
            rev.append(dict(project=p, package=pkg, bsl_release=seen_bsl[pkg][1], bsl_date=seen_bsl[pkg][0],
                            later_release=ver, later_date=pub, later_status=st))
            del seen_bsl[pkg]  # count the first move away per artifact spell
rv = pd.DataFrame(rev)
rv.to_csv(O / "reversions.csv", index=False)
by = rv.groupby("later_status").project.nunique().to_dict() if len(rv) else {}
out["B_reversions"] = dict(
    projects_ever_on_bsl_after_event=len(first_bsl),
    artifact_moves_away_from_bsl=len(rv),
    projects_with_move_by_destination=by,
    projects_with_any_move=int(rv.project.nunique()) if len(rv) else 0,
    moves_by_half_year=(rv.assign(h=rv.later_date.str[:4] + "H" + rv.later_date.str[5:7].astype(int).gt(6).map({False: "1", True: "2"}))
                        .groupby(["h", "later_status"]).project.nunique().unstack(fill_value=0).to_dict(orient="index")
                        if len(rv) else {}),
    note="'none' means the artifact's later release declares no Akka or Pekko dependency (removal).")

# ---------- C. end of patches by port availability ----------
td = {r["project"]: r for r in csv.DictReader(open(ROOT / "outputs/step07/treatment_dates.csv", encoding="utf-8"))}
frozen = [p for p in ak if status_at(p, "2023-06-30") == "freeze"]
grp = defaultdict(lambda: defaultdict(int))
for p in frozen:
    T = (td.get(p) or {}).get("T_all", "")
    g = "ported_by_2023-09-30" if T and T[:1].isdigit() and T <= "2023-09-30" else "not_ported_by_2023-09-30"
    grp[g]["n"] += 1
    grp[g][status_at(p, "2024-06-30")] += 1
out["C_end_of_patches_by_ports"] = {k: dict(v) for k, v in grp.items()}
(O / "mechanisms.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))

# ---------- B (Elasticsearch counterpart): moves away from restricted versions ----------
# Same rule as B: a later release of the same artifact, with a higher artifact version, that no longer declares a
# restricted (> 7.10.2) Elasticsearch version: to OpenSearch only, back to the open line, AGPL, or no Elasticsearch.
es = set(pj[(pj.event == "es") & (pj.treated == 1)].project)
erel = defaultdict(list)
for r in csv.DictReader(open(ROOT / "outputs/step08/es_project_panel.csv", encoding="utf-8")):
    if r["project"] in es:
        erel[r["project"]].append((r["published"], r["package"], set(filter(None, r["kinds"].split(";"))), r["version"]))
erev, e_first = [], {}
for p, xs in erel.items():
    xs.sort()
    seen = {}
    for pub, pkg, ks, ver in xs:
        if pub < "2021-01-14":
            continue
        if "es_restricted" in ks:
            seen.setdefault(pkg, (pub, ver))
            e_first.setdefault(p, pub)
        elif pkg in seen and vt(ver) > vt(seen[pkg][1]):
            dest = ("opensearch" if "opensearch" in ks and not ks & {"es_open", "es_agpl", "es_unresolved"} else
                    "dual" if "opensearch" in ks else "es_open" if "es_open" in ks else
                    "es_agpl" if "es_agpl" in ks else "other_or_none")
            erev.append(dict(project=p, package=pkg, restr_release=seen[pkg][1], restr_date=seen[pkg][0],
                             later_release=ver, later_date=pub, destination=dest))
            del seen[pkg]
ev_ = pd.DataFrame(erev)
ev_.to_csv(O / "reversions_es.csv", index=False)
out["B_es_moves_from_restricted"] = dict(
    projects_ever_on_restricted_after_event=len(e_first),
    projects_with_any_move=int(ev_.project.nunique()) if len(ev_) else 0,
    projects_with_move_by_destination=ev_.groupby("destination").project.nunique().to_dict() if len(ev_) else {})
(O / "mechanisms.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out["B_es_moves_from_restricted"], indent=1))
