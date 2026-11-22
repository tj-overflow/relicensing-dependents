"""Step 15a (R1): scripted freeze count for the launch design (replaces a scratch count used in the first draft).

Population: Akka active non-adopters, i.e. act240 = 1 and y1 = 0, for A27 (and A26, A25 for comparison).
Window: releases in (L, L+240]. Per project, from outputs/step13/lu/cohorts.csv (built by step13g):
  any_old   : at least one release declares the predecessor line (old240 = 1)
  any_pekko : at least one release declares Pekko (pk240 = 1)
  last state: declared state of the last release in the window (st240: old / pekko / none / new)
Exclusive classes, by the last release: kept the old line / Pekko / no core Akka / new-line milestone (not stable).
Output: outputs/step15/freeze_count.json
"""
from pathlib import Path
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
O = ROOT / "outputs/step15"
O.mkdir(parents=True, exist_ok=True)
d = pd.read_csv(ROOT / "outputs/step13/lu/cohorts.csv")
out = {}
for coh in ["A25", "A26", "A27"]:
    na = d[(d.cohort == coh) & (d.act240 == 1) & (d.y1 == 0)]
    out[coh] = {
        "active_non_adopters": int(len(na)),
        "any_release_declares_old_line": int(na.old240.sum()),
        "any_release_declares_pekko": int(na.pk240.sum()),
        "last_release_state": {k: int(v) for k, v in na.st240.value_counts().items()},
        "never_declares_old_line": sorted(na.loc[na.old240 == 0, "project"].tolist()),
    }
(O / "freeze_count.json").write_text(json.dumps(out, indent=1))
print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "never_declares_old_line"} for k, v in out.items()}, indent=1))
print("A27 never old:", out["A27"]["never_declares_old_line"])
