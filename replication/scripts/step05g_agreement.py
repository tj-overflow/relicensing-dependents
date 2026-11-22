"""Step 5g: agreement between registry coding and repository hand-coding; exposure-proxy test.

Inputs : outputs/step05/validation_sample.csv, hand_coded.csv, data/raw/step05/owners.json,
         outputs/step05/project_flags.csv
Outputs: outputs/step05/agreement.json, outputs/step05/validation_merged.csv
"""
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
O = ROOT / "outputs/step05"
MAP = {"dual_or_partial": "dual"}
samp = {r["project"]: r for r in csv.DictReader(open(O / "validation_sample.csv", encoding="utf-8"))}
hand = {r["project"]: r for r in csv.DictReader(open(O / "hand_coded.csv", encoding="utf-8"))}
owners = json.loads((ROOT / "data/raw/step05/owners.json").read_text())
flags = {r["project"]: r for r in csv.DictReader(open(O / "project_flags.csv", encoding="utf-8"))}


def kappa(pairs):
    n = len(pairs)
    po = sum(a == b for a, b in pairs) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / n ** 2
    return round((po - pe) / (1 - pe), 3) if pe < 1 else None


rows = []
for p, h in hand.items():
    s = samp[p]
    reg = MAP.get(s["stratum"], s["stratum"])
    o = owners.get(s["repo"].split("/")[1], {})
    found = flags[p]["foundation"] != "" or h["maintainer_hand"] == "foundation"
    a1 = int(o.get("type") == "Organization" and not found)
    a2 = int(a1 or (o.get("type") == "User" and bool((o.get("company") or "").strip())))
    rows.append(dict(project=p, stratum=s["stratum"], weight=float(s["weight"]), registry=reg, repo=h["repo_outcome"],
                     shaded=int(h["shaded"]), agree=int(reg == h["repo_outcome"]),
                     adjudicated=h["adjudicated"], registry_correct=int(reg == h["adjudicated"]),
                     sd_registry=int(reg in ("switch", "dual")), sd_repo=int(h["repo_outcome"] in ("switch", "dual")),
                     maintainer_hand=h["maintainer_hand"], exposed_hand=int(h["maintainer_hand"] == "company"),
                     A1=a1, A2=a2, owner_type=o.get("type"), vendor=flags[p]["vendor"], uncertain=h["uncertain"]))

coded = [r for r in rows if r["repo"] != "unclear"]
w = sum(r["weight"] for r in coded)
res = dict(n_hand_coded=len(rows), n_unclear=len(rows) - len(coded),
           agree_raw=round(sum(r["agree"] for r in coded) / len(coded), 3),
           agree_weighted=round(sum(r["weight"] * r["agree"] for r in coded) / w, 3),
           agree_by_stratum={s: f"{sum(r['agree'] for r in coded if r['stratum'] == s)}/{sum(1 for r in coded if r['stratum'] == s)}"
                             for s in sorted({r["stratum"] for r in coded})},
           switch_or_dual_agree_raw=round(sum(r["sd_registry"] == r["sd_repo"] for r in coded) / len(coded), 3),
           switch_or_dual_agree_weighted=round(sum(r["weight"] * (r["sd_registry"] == r["sd_repo"]) for r in coded) / w, 3),
           kappa_5way=kappa([(r["registry"], r["repo"]) for r in coded]),
           kappa_switch_or_dual=kappa([(r["sd_registry"], r["sd_repo"]) for r in coded]),
           registry_accuracy_vs_adjudicated_raw=round(sum(r["registry_correct"] for r in coded) / len(coded), 3),
           registry_accuracy_vs_adjudicated_weighted=round(sum(r["weight"] * r["registry_correct"] for r in coded) / w, 3),
           shaded=[r["project"] for r in rows if r["shaded"]],
           confusion=Counter(f"{r['registry']}->{r['repo']}" for r in coded if not r["agree"]),
           disagreements=[(r["project"], r["registry"], r["repo"]) for r in coded if not r["agree"]])
ex = [r for r in rows if r["maintainer_hand"] != "foundation"]
for a in ("A1", "A2"):
    pairs = [(r[a], r["exposed_hand"]) for r in ex]
    res[f"exposure_{a}"] = dict(n=len(ex), agree=round(sum(x == y for x, y in pairs) / len(pairs), 3), kappa=kappa(pairs),
                                false_pos=[r["project"] for r in ex if r[a] and not r["exposed_hand"]],
                                false_neg=[r["project"] for r in ex if not r[a] and r["exposed_hand"]])
res["maintainer_hand_counts"] = Counter(r["maintainer_hand"] for r in rows)
(O / "agreement.json").write_text(json.dumps(res, indent=1, default=dict))
with open(O / "validation_merged.csv", "w", newline="", encoding="utf-8") as f:
    wr = csv.DictWriter(f, fieldnames=list(rows[0]))
    wr.writeheader()
    wr.writerows(rows)
print(json.dumps(res, indent=1, default=dict))
