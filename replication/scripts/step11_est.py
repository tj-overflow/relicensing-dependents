"""Shared estimation routines for Step 11 (imported by step11b, step11c, step11d).

Weighted two-way fixed effects by alternating projections; cluster-robust variance by owner with the small-sample
factor G/(G-1) * (N-1)/(N-K), where K counts the regressors and the quarter fixed effects (project fixed effects
are nested in owner clusters and are not counted, as in fixest/reghdfe).
Propensity weights: ATT odds from a logit of treatment on pre-event covariates, trimmed to [0.05, 0.95].
"""
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

COVS = {"akka": ["log_rel", "log_art", "scala3_pre", "age_years_at_event"],
        "es": ["log_rel", "log_art", "age_years_at_event", "bom_pre"]}


def weights(projects, event):
    """ATT weights: logit of treatment on the pre-event covariates, trimmed to [0.05, 0.95]."""
    b = projects[projects.event == event].copy()
    b["log_rel"], b["log_art"] = np.log1p(b.rel_per_year_pre), np.log1p(b.n_artifacts)
    ps = smf.logit("treated ~ " + " + ".join(COVS[event]), data=b).fit(disp=0)
    b["ps"] = ps.predict(b)
    n0 = len(b)
    b = b[(b.ps >= 0.05) & (b.ps <= 0.95)].copy()
    b["w"] = np.where(b.treated == 1, 1.0, b.ps / (1 - b.ps))
    return b, n0 - len(b)


def smd_table(b, event):
    cols = {"akka": ["rel_per_year_pre", "n_artifacts", "scala3_pre", "age_years_at_event"],
            "es": ["rel_per_year_pre", "n_artifacts", "age_years_at_event", "bom_pre"]}[event]
    out = []
    t = b.treated.values
    for c in cols:
        x = b[c].astype(float).values
        s = np.sqrt((x[t == 1].var() + x[t == 0].var()) / 2)

        def d(w):
            return (np.average(x[t == 1], weights=w[t == 1]) - np.average(x[t == 0], weights=w[t == 0])) / s if s > 0 else 0.0
        out.append(dict(covariate=c, mean_treated=round(x[t == 1].mean(), 3), mean_cmp=round(x[t == 0].mean(), 3),
                        smd_raw=round(d(np.ones(len(x))), 3), smd_weighted=round(d(b.w.values), 3)))
    return out


def demean(M, fes, w, tol=1e-10, maxit=10000):
    """Weighted alternating projections: residualize columns of M on the fixed effects in fes (list of int codes)."""
    M = M.astype(float).copy()
    for _ in range(maxit):
        old = M.copy()
        for f in fes:
            sw = np.bincount(f, weights=w)
            for j in range(M.shape[1]):
                M[:, j] -= (np.bincount(f, weights=w * M[:, j]) / sw)[f]
        if np.max(np.abs(M - old)) < tol:
            return M
    raise RuntimeError("demeaning did not converge")


class Fit:
    pass


def twfe(d, y, xcols, w=None, cluster="owner", fe=("project", "quarter")):
    """y on xcols with fixed effects; returns coefficients, cluster-robust SEs and the pieces for inference."""
    d = d.reset_index(drop=True)
    w = np.ones(len(d)) if w is None else np.asarray(w, float)
    fes = [pd.factorize(d[f])[0] for f in fe]
    M = demean(np.column_stack([d[y].values] + [d[c].values for c in xcols]), fes, w)
    yt, X = M[:, 0], M[:, 1:]
    XtWX = X.T @ (X * w[:, None])
    beta = np.linalg.solve(XtWX, X.T @ (w * yt))
    e = yt - X @ beta
    g = pd.factorize(d[cluster])[0]
    G = g.max() + 1
    S = np.zeros((G, X.shape[1]))
    np.add.at(S, g, X * (w * e)[:, None])
    inv = np.linalg.inv(XtWX)
    n, k = len(d), X.shape[1] + (d[fe[1]].nunique() - 1 if len(fe) > 1 else 0)
    V = inv @ (S.T @ S) @ inv * G / (G - 1) * (n - 1) / (n - k)
    f = Fit()
    f.beta, f.V, f.se = beta, V, np.sqrt(np.diag(V))
    f.names, f.n, f.G, f.X, f.yt, f.e, f.w, f.g, f.inv, f.k = list(xcols), n, G, X, yt, e, w, g, inv, k
    return f


def wald(f, idx):
    """Cluster-robust Wald F for coefficients idx; F(q, G-1) reference."""
    from scipy import stats
    b, V = f.beta[idx], f.V[np.ix_(idx, idx)]
    q = len(idx)
    F = float(b @ np.linalg.solve(V, b)) / q
    return F, float(stats.f.sf(F, q, f.G - 1))


def summary(f, name, extra=None):
    from scipy import stats
    i = f.names.index(name)
    b, se = float(f.beta[i]), float(f.se[i])
    t = stats.t.ppf(0.975, f.G - 1)
    out = dict(coef=round(b, 4), se=round(se, 4), ci95=[round(b - t * se, 4), round(b + t * se, 4)],
               p=round(float(2 * stats.t.sf(abs(b / se), f.G - 1)), 4), n_obs=f.n, n_clusters=int(f.G))
    if extra:
        out.update(extra)
    return out
