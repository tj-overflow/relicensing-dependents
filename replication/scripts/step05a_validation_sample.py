"""Step 5a: draw the validation sample (fixed seed) from active risk-set projects.

Design: census of registry-'removed' projects (needed anyway to detect shading), plus a random
draw within each other registry outcome. Sampling weights = stratum size / sampled in stratum.
Non-GitHub projects (maven:* fallback) are excluded from the frame because there is no repository
to code, except where a repository is mapped by hand in REPO_MAP.
Outputs: outputs/step05/validation_sample.csv
"""
import csv
import random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "step05"
OUT.mkdir(parents=True, exist_ok=True)
EVENT, HORIZON = "2022-09-07", "2025-09-30"
SEED = 20220907
N = {"freeze": 14, "switch": 10, "dual_or_partial": 9, "upgrade": 7}  # 'removed' is a census
REPO_MAP = {"maven:org.opendaylight.odlparent": "github.com/opendaylight/odlparent"}

risk = [r for r in csv.DictReader(open(ROOT / "outputs/step04/risk_set.csv", encoding="utf-8")) if r["active_post"] == "1"]
panel = list(csv.DictReader(open(ROOT / "outputs/step04/project_panel.csv", encoding="utf-8")))
last_rel = defaultdict(str)
for p in panel:
    if EVENT <= p["published"] <= HORIZON and p["published"] > last_rel[p["project"]]:
        last_rel[p["project"]] = p["published"]

strata = defaultdict(list)
for r in risk:
    repo = REPO_MAP.get(r["project"], r["project"])
    if repo.startswith("github.com/"):
        strata[r["outcome_at_horizon"]].append(r)
pop = defaultdict(int)
for r in risk:
    pop[r["outcome_at_horizon"]] += 1

rng = random.Random(SEED)
rows = []
for s in sorted(strata):
    frame = sorted(strata[s], key=lambda r: r["project"])
    pick = frame if s == "removed" else rng.sample(frame, N[s])
    for r in pick:
        rows.append(dict(project=r["project"], repo=REPO_MAP.get(r["project"], r["project"]), stratum=s,
                         stratum_pop=pop[s], stratum_n=len(pick), weight=round(pop[s] / len(pick), 4),
                         last_release_by_horizon=last_rel[r["project"]]))
with open(OUT / "validation_sample.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
print(len(rows), {s: sum(1 for r in rows if r["stratum"] == s) for s in strata}, dict(pop))

# --- replacements (added after fetching): repositories deleted or private on GitHub --------------
# Each unavailable non-census project is replaced by a seeded draw from the same stratum.
# Census ('removed') projects cannot be replaced; they stay in the file as unavailable.
UNAVAILABLE = {"github.com/emartech/escher-akka-http", "github.com/guardian/membership-common",
               "github.com/alibaba/ververica-connectors", "github.com/wuyushuo/spring-boxes",
               "github.com/cafienne/cafienne-engine", "github.com/romansky/nozzler"}
rng2 = random.Random(SEED + 1)
taken = {r["project"] for r in rows}
for r in rows:
    r["available"] = int(r["project"] not in UNAVAILABLE)
    r["replacement_for"] = ""
extra = []
for r in rows:
    if r["available"] or r["stratum"] == "removed":
        continue
    frame = sorted((x for x in strata[r["stratum"]] if x["project"] not in taken and x["project"] not in UNAVAILABLE),
                   key=lambda x: x["project"])
    x = rng2.choice(frame)
    taken.add(x["project"])
    extra.append(dict(project=x["project"], repo=x["project"], stratum=r["stratum"], stratum_pop=r["stratum_pop"],
                      stratum_n=r["stratum_n"], weight=r["weight"], last_release_by_horizon=last_rel[x["project"]],
                      available=1, replacement_for=r["project"]))
rows += extra
with open(OUT / "validation_sample.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
print("replacements:", [(e["replacement_for"], e["project"]) for e in extra])
