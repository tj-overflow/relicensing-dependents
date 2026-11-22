"""Step 14d: agreement between the human coder(s) and coder A on the validation sample.

Decision rule:

  Primary targets, repository level, on the 60-unit validation sample:
    LICENCE_ANY = LEGAL_OWN or LEGAL_USERS or LICENCE_UNSPEC  (the "licence given as a reason" row)
    COMPAT
  PASS     if Cohen's kappa >= 0.60 for both.
  PARTIAL  if one is >= 0.60 and the other is in [0.40, 0.60).
  FAIL     otherwise.
  Hold-up check: if the human codes TRUST in >= 5 units (coder A: 1), the claim
  "hold-up language is almost absent" is revised whatever the kappa.
  On FAIL or PARTIAL the paper reports the human-coded shares on the sample as the
  primary text evidence and the model-coded full-sample shares as supplementary.

  Secondary (reported, no decision attached): R, every single code, LEGAL_SPEC
  (LEGAL_OWN or LEGAL_USERS), action (multi-category kappa). Kappa CIs are
  percentile bootstraps over units (2,000 draws, seed 20261112). Units with R = 0
  for a coder count as 0 on every code for that coder.

Inputs:  validation/human_codes_*.csv (exported by validation/human_coding.html),
         outputs/step12/text_coded_projects.csv (coder A)
Outputs: outputs/step14/validation_results.json, validation_disagreements.csv
         (codes only, no text)
Usage:   python step14d_validation_score.py [--files validation/human_codes_XX.csv ...]
"""
from pathlib import Path
import argparse, glob, json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/step14"
CODES = ["LEGAL_OWN", "LEGAL_USERS", "LICENCE_UNSPEC", "USER_REQUEST", "TRUST",
         "AGEING", "COMPAT", "COORD", "COST"]
SEED, B = 20261112, 2000


def kappa(a, b):
    a, b = np.asarray(a), np.asarray(b)
    cats = np.union1d(a, b)
    po = np.mean(a == b)
    pe = sum(np.mean(a == c) * np.mean(b == c) for c in cats)
    return float("nan") if pe == 1 else float((po - pe) / (1 - pe))


def boot_ci(a, b, rng):
    n = len(a)
    ks = [kappa(a[i], b[i]) for i in (rng.integers(0, n, n) for _ in range(B))]
    ks = np.array([k for k in ks if not np.isnan(k)])
    return [float(np.quantile(ks, 0.025)), float(np.quantile(ks, 0.975))] if len(ks) else [None, None]


def derive(df):
    df = df.copy()
    for c in CODES:
        df[c] = df[c].where(df.R == 1, 0).astype(int)
    df["LICENCE_ANY"] = df[["LEGAL_OWN", "LEGAL_USERS", "LICENCE_UNSPEC"]].max(axis=1)
    df["LEGAL_SPEC"] = df[["LEGAL_OWN", "LEGAL_USERS"]].max(axis=1)
    df["action"] = df.action.where(df.R == 1, "NA").fillna("NA").replace("", "NA")
    return df


def coder_a():
    a = pd.read_csv(ROOT / "outputs/step12/text_coded_projects.csv")
    sets = a.codes.fillna("").str.split(";")
    for c in CODES:
        a[c] = sets.apply(lambda s: int(c in s))
    return derive(a[["event", "repo", "R", "action"] + CODES])


def score(h, a, rng):
    m = h.merge(a, on=["event", "repo"], suffixes=("_h", "_a"), validate="one_to_one")
    res = {"n_units": len(m), "by_target": {}}
    for t in ["R", "LICENCE_ANY", "COMPAT", "TRUST", "LEGAL_SPEC"] + CODES + ["action"]:
        x, y = m[f"{t}_h"].to_numpy(), m[f"{t}_a"].to_numpy()
        r = {"kappa": kappa(x, y), "ci95": boot_ci(x, y, rng), "pct_agree": float(np.mean(x == y))}
        if t != "action":
            r.update(human_n=int(x.sum()), coderA_n=int(y.sum()))
        res["by_target"][t] = r
    k1, k2 = res["by_target"]["LICENCE_ANY"]["kappa"], res["by_target"]["COMPAT"]["kappa"]
    if k1 >= 0.6 and k2 >= 0.6:
        verdict = "PASS"
    elif max(k1, k2) >= 0.6 and min(k1, k2) >= 0.4:
        verdict = "PARTIAL"
    else:
        verdict = "FAIL"
    res["verdict"] = verdict
    res["trust_revision"] = bool(res["by_target"]["TRUST"]["human_n"] >= 5)
    shares = {}
    for ev, g in m.groupby("event"):
        rel_h, rel_a = g[g.R_h == 1], g[g.R_a == 1]
        shares[ev] = {
            "relevant_h": len(rel_h), "relevant_a": len(rel_a),
            **{f"{t}_share_h": float(rel_h[f"{t}_h"].mean()) if len(rel_h) else None for t in ["LICENCE_ANY", "LEGAL_SPEC", "COMPAT", "TRUST", "USER_REQUEST"]},
            **{f"{t}_share_a": float(rel_a[f"{t}_a"].mean()) if len(rel_a) else None for t in ["LICENCE_ANY", "LEGAL_SPEC", "COMPAT", "TRUST", "USER_REQUEST"]},
        }
    res["sample_shares_by_event"] = shares
    keep = ["event", "repo"] + [f"{t}_{s}" for t in ["R", "LICENCE_ANY", "COMPAT", "TRUST", "action"] + CODES for s in "ha"]
    diff = m[(m.R_h != m.R_a) | (m.LICENCE_ANY_h != m.LICENCE_ANY_a) | (m.COMPAT_h != m.COMPAT_a) | (m.TRUST_h != m.TRUST_a)]
    return res, diff[keep]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--files", nargs="*", default=sorted(glob.glob(str(ROOT / "validation/human_codes_*.csv"))))
    p.add_argument("--out", default=str(OUT))
    args = p.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    a = coder_a()
    results, diffs, humans = {}, [], {}
    for f in args.files:
        h = pd.read_csv(f, keep_default_na=False)
        missing = int((h.R.astype(str) == "").sum())
        if missing:
            raise SystemExit(f"{f}: {missing} repositories not coded yet")
        coder = str(h.coder.iloc[0]) or Path(f).stem
        h["R"] = h.R.astype(int)
        h = derive(h[["event", "repo", "R", "action"] + CODES])
        humans[coder] = h
        rng = np.random.default_rng(SEED)
        results[coder], d = score(h, a, rng)
        diffs.append(d.assign(coder=coder))
    if len(humans) >= 2:
        (c1, h1), (c2, h2) = list(humans.items())[:2]
        mm = h1.merge(h2, on=["event", "repo"], suffixes=("_1", "_2"))
        results["human_vs_human"] = {t: kappa(mm[f"{t}_1"], mm[f"{t}_2"]) for t in ["R", "LICENCE_ANY", "COMPAT", "TRUST"] + CODES}
        results["human_vs_human"]["coders"] = [c1, c2]
    (out / "validation_results.json").write_text(json.dumps(results, indent=1))
    if diffs:
        pd.concat(diffs).to_csv(out / "validation_disagreements.csv", index=False)
    for c, r in results.items():
        if c == "human_vs_human":
            continue
        bt = r["by_target"]
        print(f"[{c}] n={r['n_units']} verdict={r['verdict']} trust_revision={r['trust_revision']}")
        for t in ["R", "LICENCE_ANY", "COMPAT", "TRUST", "LEGAL_SPEC", "action"]:
            print(f"   {t:12s} kappa {bt[t]['kappa']:.2f} {bt[t]['ci95']}  agree {bt[t]['pct_agree']:.2f}")


if __name__ == "__main__":
    main()
