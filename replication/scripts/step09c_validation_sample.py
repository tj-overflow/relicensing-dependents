"""Step 9c: Elasticsearch validation sample (fixed seed) from active non-vendor direct risk-set projects.

Design mirrors step05a: census of registry 'removed' and 'es_version_unresolved' projects, plus seeded
draws within each other registry outcome at the main horizon (2024-11-11). CodeLibs projects form
their own stratum (2 draws) so the dominant switcher owner is checked without crowding the switch stratum.
Non-GitHub projects (maven:* fallback) are excluded from the frame.
Output: outputs/step09/validation_sample.csv (stratum weights = stratum population / sampled)
"""
import csv
import random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
O = ROOT / "outputs/step09"
O.mkdir(parents=True, exist_ok=True)
EVENT, HORIZON, SEED = "2021-01-14", "2024-11-11", 20210114
N = {"freeze": 8, "upgrade": 7, "switch": 4, "dual": 5, "vendor_open": 5, "codelibs": 2}
CENSUS = {"removed", "es_version_unresolved"}

risk = [r for r in csv.DictReader(open(ROOT / "outputs/step08/es_risk_set.csv", encoding="utf-8"))
        if r["group"] == "direct" and r["active_post"] == "1" and r["vendor"] == "0"
        and (r["fork_affiliated"] == "0" or r["owner"] == "opendistro-for-elasticsearch")]
# The frame is the Step 8 risk set as it stood when the sample was drawn; Open Distro (AWS) was reclassified
# as fork-affiliated in Step 9 and is excluded from replacement draws below.
last_rel = defaultdict(str)
for p in csv.DictReader(open(ROOT / "outputs/step08/es_project_panel.csv", encoding="utf-8")):
    if EVENT <= p["published"] <= HORIZON and p["published"] > last_rel[p["project"]]:
        last_rel[p["project"]] = p["published"]


def stratum(r):
    return "codelibs" if r["owner"] == "codelibs" else r["outcome_2024_11"]


pop, frame = defaultdict(int), defaultdict(list)
for r in risk:
    pop[stratum(r)] += 1
    if r["project"].startswith("github.com/"):
        frame[stratum(r)].append(r)
rng = random.Random(SEED)
rows = []
for s in sorted(frame):
    f = sorted(frame[s], key=lambda r: r["project"])
    pick = f if s in CENSUS else rng.sample(f, min(N.get(s, 0), len(f)))
    for r in pick:
        rows.append(dict(project=r["project"], repo=r["project"], stratum=s, stratum_pop=pop[s], stratum_n=len(pick),
                         weight=round(pop[s] / len(pick), 4), last_release_by_horizon=last_rel[r["project"]]))
with open(O / "validation_sample.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
print(len(rows), {s: sum(1 for r in rows if r["stratum"] == s) for s in frame}, dict(pop))

# --- replacements (added after fetching): repositories deleted on GitHub or without a usable commit -----
# Each unavailable non-census project is replaced by a seeded draw from the same stratum.
# Census strata ('removed', 'es_version_unresolved') cannot be replaced; they stay as unavailable.
UNAVAILABLE = {"github.com/groupby/common", "github.com/matevip/matecloud", "github.com/fangjinuo/es-mvc",
               "github.com/skroutz/dynamic-stemmer-override", "github.com/haosenwei/g4m-com",
               "github.com/microservice-systems/log4j2-elasticsearch-appender"}
rng2 = random.Random(SEED + 1)
taken = {r["project"] for r in rows}
for r in rows:
    r["available"] = int(r["project"] not in UNAVAILABLE)
    r["replacement_for"] = ""
extra = []
for r in rows:
    if r["available"] or r["stratum"] in CENSUS:
        continue
    f = sorted((x for x in frame[r["stratum"]] if x["project"] not in taken and x["project"] not in UNAVAILABLE
               and x["owner"] != "opendistro-for-elasticsearch"),
               key=lambda x: x["project"])
    x = rng2.choice(f)
    taken.add(x["project"])
    extra.append(dict(project=x["project"], repo=x["project"], stratum=r["stratum"], stratum_pop=r["stratum_pop"],
                      stratum_n=r["stratum_n"], weight=r["weight"], last_release_by_horizon=last_rel[x["project"]],
                      available=1, replacement_for=r["project"]))
rows += extra
with open(O / "validation_sample.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
print("replacements:", [(e["replacement_for"], e["project"]) for e in extra])
