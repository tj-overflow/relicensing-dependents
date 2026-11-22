"""Step 6d: Scala 3 confound for switching, and descriptive outcome timelines.

Population: active, non-vendor projects of outputs/step05/risk_set_v2.csv.
  - Scala 3 status at the first switch: 'changed' if the project's first _3 artifact is within 31 days of
    its first Pekko release; 'already' if earlier; 'none' if no _3 artifact by 31 days after the switch.
    Step 1 test: >= 15 switchers whose Scala status is unchanged ('already' or 'none').
  - Switching (S or D by the horizon) by Scala 3 status before the event x Akka HTTP use before the event.
  - Switching among projects that never published a Scala 3 artifact by the horizon.
  - Monthly cumulative share with a first switch, by Scala 3 status before the event.
Outputs: outputs/step06/scala3_confound.json, timeline_monthly.csv
"""
import csv
import json
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
O = ROOT / "outputs/step06"
HORIZON = "2025-09-30"
rows = [r for r in csv.DictReader(open(ROOT / "outputs/step05/risk_set_v2.csv", encoding="utf-8"))
        if r["active_post"] == "1" and r["vendor"] == "0"]


def days(a, b):
    return (date.fromisoformat(a) - date.fromisoformat(b)).days


SD = ("switch", "dual_or_partial")
res = {}
sw = [r for r in rows if r["first_switch_v2"]]
status = Counter()
per = []
for r in sw:
    f3, fs = r["first_scala3_release"], r["first_switch_v2"]
    if f3 and abs(days(f3, fs)) <= 31:
        s = "changed_at_switch"
    elif f3 and days(f3, fs) < -31:
        s = "already_scala3"
    else:
        s = "no_scala3_at_switch"
    status[s] += 1
    per.append((r["project"], s))
res["switchers"] = len(sw)
res["scala3_status_at_first_switch"] = dict(status)
res["switchers_with_unchanged_scala_status"] = status["already_scala3"] + status["no_scala3_at_switch"]
res["step1_test_ge_15"] = res["switchers_with_unchanged_scala_status"] >= 15

tab = {}
for s3 in ("0", "1"):
    for http in (0, 1):
        g = [r for r in rows if r["scala3_pre_event"] == s3 and int("http" in r["akka_modules_pre"]) == http]
        k = sum(r["outcome_v2"] in SD for r in g)
        tab[f"scala3_pre={s3}, http_user={http}"] = dict(n=len(g), switch_or_dual=k,
                                                         share=round(k / len(g), 3) if g else None)
res["switch_or_dual_by_scala3_pre_and_http"] = tab
never = [r for r in rows if not r["first_scala3_release"] or r["first_scala3_release"] > HORIZON]
k = sum(r["outcome_v2"] in SD for r in never)
res["never_scala3_by_horizon"] = dict(n=len(never), switch_or_dual=k, share=round(k / len(never), 3),
                                      outcomes=dict(Counter(r["outcome_v2"] for r in never)))
ever = [r for r in rows if r not in never]
k = sum(r["outcome_v2"] in SD for r in ever)
res["scala3_by_horizon"] = dict(n=len(ever), switch_or_dual=k, share=round(k / len(ever), 3),
                                outcomes=dict(Counter(r["outcome_v2"] for r in ever)))
res["outcomes_by_scala3_pre"] = {s3: dict(Counter(r["outcome_v2"] for r in rows if r["scala3_pre_event"] == s3))
                                 for s3 in ("0", "1")}

# monthly cumulative share with a first switch
months = [f"{y}-{m:02d}" for y in range(2022, 2026) for m in range(1, 13) if "2022-09" <= f"{y}-{m:02d}" <= "2025-09"]
out = []
for mth in months:
    row = {"month": mth}
    for lab, g in (("all", rows), ("scala3_pre_0", [r for r in rows if r["scala3_pre_event"] == "0"]),
                   ("scala3_pre_1", [r for r in rows if r["scala3_pre_event"] == "1"]),
                   ("never_scala3", never)):
        row[lab] = round(sum(1 for r in g if r["first_switch_v2"] and r["first_switch_v2"][:7] <= mth) / len(g), 4)
    out.append(row)
with open(O / "timeline_monthly.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(out[0]))
    w.writeheader()
    w.writerows(out)
res["n_active_nonvendor"] = len(rows)
(O / "scala3_confound.json").write_text(json.dumps(res, indent=1))
print(json.dumps(res, indent=1))
