"""Step 9g: agreement between registry outcome (Step 8, horizon 2024-11-11) and hand coding (Step 9).

Two hand-coding versions: strict codebook (provided scope excluded) and provided-as-declared (the registry
rule, which excludes only test and optional). Reports raw and stratum-weighted agreement, Cohen's kappa,
the confusion matrix, and the disagreements. Projects coded 'unclear' are reported and excluded from kappa.
Output: outputs/step09/agreement.json
"""
import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
O = ROOT / "outputs/step09"
sample = {r["project"]: r for r in csv.DictReader(open(O / "validation_sample.csv", encoding="utf-8"))}
reg = {r["project"]: r for r in csv.DictReader(open(ROOT / "outputs/step08/es_risk_set.csv", encoding="utf-8"))}
hand = list(csv.DictReader(open(O / "hand_coded.csv", encoding="utf-8")))


def kappa(pairs):
    n = len(pairs)
    po = sum(a == b for a, b in pairs) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / n ** 2
    return round((po - pe) / (1 - pe), 3) if pe < 1 else 1.0


res = {}
for col in ("coded", "coded_provided_as_declared"):
    rows = []
    for h in hand:
        r = reg[h["project"]]
        rows.append(dict(project=h["project"], registry=r["outcome_2024_11"], hand=h[col],
                         w=float(sample[h["project"]]["weight"]), note=h["note"]))
    clear = [x for x in rows if x["hand"] != "unclear"]
    agree = [x for x in clear if x["registry"] == x["hand"]]
    res[col] = dict(
        n_coded=len(rows), n_unclear=len(rows) - len(clear), n_compared=len(clear),
        raw_agreement=round(len(agree) / len(clear), 3),
        weighted_agreement=round(sum(x["w"] for x in agree) / sum(x["w"] for x in clear), 3),
        kappa=kappa([(x["registry"], x["hand"]) for x in clear]),
        confusion=dict(Counter(f"{x['registry']} -> {x['hand']}" for x in clear)),
        disagreements=[{k: x[k] for k in ("project", "registry", "hand", "note")} for x in clear if x["registry"] != x["hand"]],
        unclear=[{k: x[k] for k in ("project", "registry", "note")} for x in rows if x["hand"] == "unclear"])
hk = {h["project"]: h for h in hand}
res["kind_vs_registry_stratum"] = dict(Counter(
    f"{hk[p]['kind']}" for p in hk))
res["bom_managed_hand"] = sum(int(h["bom_managed"]) for h in hand)
(O / "agreement.json").write_text(json.dumps(res, indent=1))
for col in ("coded", "coded_provided_as_declared"):
    print(col, {k: v for k, v in res[col].items() if k not in ("confusion",)})
