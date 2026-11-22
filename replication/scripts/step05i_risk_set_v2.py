"""Step 5i: corrected outcome panel (risk set v2) with Step 5 flags.

Starts from outputs/step04/risk_set.csv (already with the repository alias map applied in step04c)
and applies the corrections established in Step 5:
  - shading override : projects whose published POMs hide a shaded Pekko (hand-verified list)
  - wrapper override : projects switching through third-party Pekko wrappers (step05h; hand-verified)
  - flags            : vendor, foundation, own licence, Scala 3, Play use, provided-only, module groups
  - unresolved flag  : 'freeze' resting only on Akka declarations whose version is set by an external BOM
Output: outputs/step05/risk_set_v2.csv, outputs/step05/counts_v2.json
"""
import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
O = ROOT / "outputs/step05"
# project: (corrected outcome, first Pekko release date, evidence)
OVERRIDE = {
    "github.com/apache/flink": ("switch", "2023-10-18", "Flink 1.18.0 shades Pekko 1.x in flink-rpc-akka (FLINK-32468); build files, Step 5"),
    "github.com/zalando-incubator/kanadi": ("dual_or_partial", "2023-08-15", "0.20.0 uses org.mdedetrich pekko-http/stream-circe wrappers; 0.11.x Akka line maintained"),
}
UNRESOLVED_FREEZE = {"github.com/pantheontech/lighty", "github.com/wso2/carbon-analytics-common"}

risk = list(csv.DictReader(open(ROOT / "outputs/step04/risk_set.csv", encoding="utf-8")))
flags = {r["project"]: r for r in csv.DictReader(open(O / "project_flags.csv", encoding="utf-8"))}
rows = []
for r in risk:
    f = flags[r["project"]]
    out = dict(r)
    out["outcome_v2"], out["first_switch_v2"], out["correction"] = r["outcome_at_horizon"], r["first_switch"], ""
    if r["project"] in OVERRIDE:
        o, d, ev = OVERRIDE[r["project"]]
        out["outcome_v2"], out["first_switch_v2"], out["correction"] = o, min(x for x in (d, r["first_switch"]) if x), ev
        out["ever_switched"] = 1
    out["freeze_version_unresolved"] = int(r["project"] in UNRESOLVED_FREEZE)
    for k in ("owner", "vendor", "foundation", "own_licence_pre", "own_licence_changed", "scala3_pre_event",
              "first_scala3_release", "play_user_pre", "akka_provided_or_testkit_only", "akka_modules_pre"):
        out[k] = f[k]
    rows.append(out)
with open(O / "risk_set_v2.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
act = [r for r in rows if r["active_post"] == "1"]
main = [r for r in act if r["vendor"] == "0"]
c = dict(risk_set=len(rows), active=len(act), active_non_vendor=len(main),
         owners_active_non_vendor=len({r["owner"] for r in main}),
         outcome_active=Counter(r["outcome_v2"] for r in act),
         outcome_active_non_vendor=Counter(r["outcome_v2"] for r in main),
         ever_switched_active=sum(int(r["ever_switched"]) for r in act),
         ever_switched_active_non_vendor=sum(int(r["ever_switched"]) for r in main),
         non_switchers_active_non_vendor=sum(1 - int(r["ever_switched"]) for r in main),
         active_post_pekko1_non_vendor=sum(int(r["active_post_pekko1"]) for r in main))
(O / "counts_v2.json").write_text(json.dumps(c, indent=1, default=dict))
print(json.dumps(c, indent=1, default=dict))
