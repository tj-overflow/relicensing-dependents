"""Step 12d (exploratory, designed after the Step 12 text evidence): the BSL change date as a test of the legal term.

Each Akka BSL version reverts to Apache 2.0 three years after its release (Step 3). Akka 2.7.0 and Akka HTTP 10.4.0
(both 2022-10-19) converted on 2025-10-19; 2.8.0 on 2026-03-16; HTTP 10.5.0 on 2026-02-21. The deps.dev snapshot
covers releases to 2026-10-31.
After conversion, moving from 2.6.21 to a converted version has no licence cost (e_i*c = 0 for that version), but the
hold-up term is unchanged: the project still depends on a supplier whose new versions are restricted. So:
  legal term binding  -> open-line projects that still release should start taking converted versions;
  hold-up / inertia   -> they should not.
Release state (core akka-* and akka-http* artifacts of com.typesafe.akka, non-test, non-optional, Maven Central only):
  open: every declared version <= 2.6.x / 10.2.x; converted: some version >= 2.7.0 / 10.4.0 and all such versions
  were converted at the release date; bsl: some version >= 2.7.0 / 10.4.0 not yet converted. Pre-releases ignored.
Windows: W0 = 2024-10-19..2025-10-18 (before any conversion), W1 = 2025-10-19..2026-10-31.
Sample: treated Akka projects whose last core/HTTP-declaring release before the window start was in state open, and
that made at least one release in the window. Outcome: the state of their releases in the window, and whether any
release declared Pekko.
Outputs: outputs/step12/conversion.json, conversion_releases.csv
"""
import csv
import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
O = ROOT / "outputs/step12"
pj = pd.read_csv(ROOT / "outputs/step11/projects.csv")
ak = set(pj[(pj.event == "akka") & (pj.treated == 1)].project)


def vt(v):
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


conv = {}
for r in csv.DictReader(open(ROOT / "data/raw/step06/supplier_versions.csv", encoding="utf-8")):
    if r["line"] in ("akka", "akka_http") and re.fullmatch(r"\d+\.\d+\.\d+", r["version"]):
        y, m, d = map(int, r["published"].split("-"))
        conv[(r["line"], r["version"])] = date(y + 3, m, min(d, 28)).isoformat()
p2proj, pstat = {}, {}
for r in csv.DictReader(open(ROOT / "outputs/step04/project_panel.csv", encoding="utf-8")):
    if r["project"] in ak:
        p2proj[(r["package"], r["version"])] = r["project"]
        pstat[(r["package"], r["version"])] = (r["published"], r["status"])
decl = defaultdict(list)
for d in csv.DictReader(open(ROOT / "data/raw/step04/release_deps.csv", encoding="utf-8")):
    k = (d["package"], d["version"])
    if k not in p2proj or d["scope"] == "test" or d["optional"] == "true" or d["dep_group"] != "com.typesafe.akka":
        continue
    v = d["dep_version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+", v or ""):
        continue
    line = "akka_http" if d["dep_artifact"].startswith("akka-http") else "akka"
    decl[k].append((line, v))
rows = []
for k, proj in p2proj.items():
    pub, st = pstat[k]
    vs = decl.get(k, [])
    restr = [(l, v) for l, v in vs if (l == "akka" and vt(v) >= (2, 7, 0)) or (l == "akka_http" and vt(v) >= (10, 4, 0))]
    if not vs:
        state = "pekko_only" if st == "pekko" else "no_core_decl"
    elif not restr:
        state = "open"
    elif all(conv.get((l, v), "9999") <= pub for l, v in restr):
        state = "converted"
    else:
        state = "bsl"
    rows.append(dict(project=proj, package=k[0], version=k[1], published=pub, status=st, state=state,
                     restricted_versions=";".join(f"{l}:{v}" for l, v in restr),
                     pekko=int(st in ("pekko", "mixed") or st == "pekko")))
R = pd.DataFrame(rows).sort_values(["project", "published"])
R.to_csv(O / "conversion_releases.csv", index=False)

out = {"conversion_dates": {f"{l} {v}": c for (l, v), c in sorted(conv.items()) if c[:4] in ("2025", "2026")}}
core = R[R.state.isin(["open", "converted", "bsl"])]
for lab, a, b in (("W0_2024-10-19_to_2025-10-18", "2024-10-19", "2025-10-18"),
                  ("W1_2025-10-19_to_2026-10-31", "2025-10-19", "2026-10-31")):
    before = core[core.published < a].groupby("project").tail(1)
    open_before = set(before[before.state == "open"].project)
    win = R[(R.published >= a) & (R.published <= b) & R.project.isin(open_before)]
    res = defaultdict(int)
    for p, g in win.groupby("project"):
        s = set(g.state)
        pek = bool((g.status.isin(["pekko", "mixed"])).any())
        if "bsl" in s:
            res["took_unconverted_bsl"] += 1
        elif "converted" in s:
            res["took_converted"] += 1
        elif "open" in s:
            res["stayed_open" + ("_and_pekko" if pek else "")] += 1
        elif pek:
            res["pekko_only"] += 1
        else:
            res["no_akka_declared"] += 1
    out[lab] = dict(open_line_projects_at_start=len(open_before), releasing_in_window=int(win.project.nunique()),
                    outcomes=dict(res))
# which converted versions were taken, and when
cv = R[R.state == "converted"]
out["converted_releases"] = dict(n_releases=len(cv), n_projects=int(cv.project.nunique()),
                                 projects=sorted(cv.project.unique().tolist()),
                                 versions=cv.restricted_versions.value_counts().head(10).to_dict())
(O / "conversion.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
