"""Step 11c: inference for the primary panel estimate.

Wild cluster bootstrap (WCR-t): Webb six-point weights, null imposed, 9,999 replications, owner clusters.
  Uses the Frisch-Waugh form: with x~ the demeaned Treated*Post and u the FE-only residual of y,
  beta* = x~'W(u*v)/x~'Wx~; residuals for the bootstrap SE come from the demeaned bootstrap outcome.
Randomization inference: owner-level treatment labels permuted within the event (owners with projects in both
  groups keep their labels), propensity weights re-estimated and trimmed for each draw, 2,000 draws, seed 20220907.
Also applied to the Elasticsearch primary estimate for comparability (descriptive).
Output: outputs/step11/inference.json
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import step11_est as E  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
O = ROOT / "outputs/step11"
pj = pd.read_csv(O / "projects.csv")
pq = pd.read_csv(O / "panel.csv")
rng = np.random.default_rng(20220907)
WEBB = np.array([-np.sqrt(1.5), -1, -np.sqrt(0.5), np.sqrt(0.5), 1, np.sqrt(1.5)])


def demean_mat(M, fes, w, tol=1e-10, maxit=10000):
    from scipy import sparse
    M = M.astype(float).copy()
    Fs = [sparse.csr_matrix((np.ones(len(f)), (f, np.arange(len(f))))) for f in fes]  # groups x obs
    sws = [F @ w for F in Fs]
    for _ in range(maxit):
        old = M.copy()
        for f, F, sw in zip(fes, Fs, sws):
            M -= ((F @ (M * w[:, None])) / sw[:, None])[f]
        if np.max(np.abs(M - old)) < tol:
            return M
    raise RuntimeError("no convergence")


def primary_sample(ev, b):
    d = pq[(pq.event == ev) & pq.period.isin(["pre", "post"]) & pq.M1.notna()].merge(
        b[["project", "group", "w"]], on=["project", "group"], how="inner").reset_index(drop=True)
    d["D"] = (d.treated * (d.period == "post")).astype(float)
    return d


def wcb(d, B=9999):
    w = d.w.values.astype(float)
    fes = [pd.factorize(d.project)[0], pd.factorize(d.quarter)[0]]
    g = pd.factorize(d.owner)[0]
    G = g.max() + 1
    M = demean_mat(np.column_stack([d.M1.values, d.D.values]), fes, w)
    u, x = M[:, 0], M[:, 1]  # u: FE-only residual of y (null imposed); x: demeaned D
    xwx = float(x @ (w * x))
    n, k = len(d), 1 + d.quarter.nunique() - 1
    fac = G / (G - 1) * (n - 1) / (n - k)

    def tstat(yt):
        b = float(x @ (w * yt)) / xwx
        e = yt - x * b
        s = np.bincount(g, weights=x * w * e, minlength=G)
        return b, b / np.sqrt(fac * (s @ s) / xwx ** 2)

    b0, t0 = tstat(M[:, 0])
    # A[:, j] = M(u * 1[cluster j]); demeaned bootstrap outcome = A @ v
    Z = np.zeros((n, G))
    Z[np.arange(n), g] = u
    A = demean_mat(Z, fes, w)
    from scipy import sparse
    Cg = sparse.csr_matrix((np.ones(n), (g, np.arange(n))))
    ts = []
    for start in range(0, B, 500):
        V = WEBB[rng.integers(0, 6, size=(G, min(500, B - start)))]
        Y = A @ V
        bs = (x * w) @ Y / xwx
        Eb = Y - np.outer(x, bs)
        S = Cg @ ((x * w)[:, None] * Eb)
        se = np.sqrt(fac * (S ** 2).sum(0) / xwx ** 2)
        ts.append(bs / se)
    ts = np.concatenate(ts)
    return dict(beta=round(b0, 4), t=round(t0, 3), p_wcb=round(float(np.mean(np.abs(ts) >= abs(t0))), 4),
                replications=B, clusters=int(G))


def ri(ev, b_obs, draws=2000):
    p = pj[pj.event == ev].copy()
    lab = p.groupby("owner").treated.agg(["min", "max"])
    pure = lab[lab["min"] == lab["max"]]
    owners, status = pure.index.values, pure["min"].values
    out = []
    for _ in range(draws):
        perm = dict(zip(owners, rng.permutation(status)))
        q = p.copy()
        m = q.owner.isin(perm)
        q.loc[m, "treated"] = q.loc[m, "owner"].map(perm)
        try:
            b, _ = E.weights(q, ev)
        except Exception:
            continue
        d = pq[(pq.event == ev) & pq.period.isin(["pre", "post"]) & pq.M1.notna()].drop(columns="treated").merge(
            b[["project", "group", "w", "treated"]], on=["project", "group"], how="inner")
        d["D"] = d.treated * (d.period == "post")
        f = E.twfe(d, "M1", ["D"], w=d.w)
        out.append(float(f.beta[0]))
    out = np.array(out)
    return dict(draws_used=int(len(out)), p_ri=round(float(np.mean(np.abs(out) >= abs(b_obs))), 4),
                perm_mean=round(float(out.mean()), 4), perm_sd=round(float(out.std()), 4),
                owners_permuted=int(len(owners)), owners_mixed_fixed=int(len(lab) - len(pure)))


res = {}
for ev in ("akka", "es"):
    b, _ = E.weights(pj, ev)
    d = primary_sample(ev, b)
    r = wcb(d)
    r.update(ri(ev, r["beta"]))
    res[f"primary {ev} M1"] = r
    print(ev, r, flush=True)
(O / "inference.json").write_text(json.dumps(res, indent=1))
