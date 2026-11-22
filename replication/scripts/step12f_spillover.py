"""Step 12f: hold-up spillover test on Lightbend's libraries whose licence did not change.

Libraries (S): com.typesafe:config, com.typesafe:ssl-config-core, com.typesafe.scala-logging:*, com.typesafe.slick:*.
All stayed Apache 2.0 / BSD-2; none depends on Akka. Play and play-json are reported apart (Play is built on Akka and
moved to the community org.playframework group in 2023; play-json moved with it).
Units: Step 11 Akka-event projects (treated Akka dependents, group akka; comparison dependents, group cmp).
Event E = 2022-09-07. Windows: pre [E-1y, E), post [E, E+2y). Placebo: pre [E-3y, E-2y), post [E-2y, E).
Per project and library set L (test scope excluded):
  user_pre  = some pre-window release declares L
  retained  = among user_pre with a post-window release, the last post-window release day declares L
  adopted   = among non-users with a post-window release, some post-window release declares L
Hold-up predicts lower retention and lower adoption among treated Akka dependents than in the comparison, beyond
the placebo-window gap. The legal channel predicts no gap. Pekko keeps config and ssl-config as its own
dependencies, so a move to Pekko does not force dropping S.
Outputs: outputs/step12/spillover.json, spillover_projects.csv
"""
import csv
import json
import re
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from scipy.stats import fisher_exact

ROOT = Path(__file__).resolve().parents[1]
O = ROOT / "outputs/step12"
E = date(2022, 9, 7)
ALIAS = {"github.com/eclipse/ditto": "github.com/eclipse-ditto/ditto",
         "github.com/balmungsan/neotypes": "github.com/neotypes/neotypes"}
SETS = {
    "S_core": lambda g, a: (g == "com.typesafe" and (a.startswith("config") or a.startswith("ssl-config")))
    or g in ("com.typesafe.scala-logging", "com.typesafe.slick"),
    "config_ssl": lambda g, a: g == "com.typesafe" and (a.startswith("config") or a.startswith("ssl-config")),
    "scala_logging": lambda g, a: g == "com.typesafe.scala-logging",
    "slick": lambda g, a: g == "com.typesafe.slick",
    "play_json": lambda g, a: g in ("com.typesafe.play", "org.playframework") and a.startswith("play-json"),
    "play_other": lambda g, a: g in ("com.typesafe.play", "org.playframework") and not a.startswith("play-json"),
}


def norm_repo(u, pkg):
    if u:
        m = re.search(r"github\.com[:/]+([^/\s]+)/([^/\s#?]+)", u)
        if m:
            r = ("github.com/" + m.group(1) + "/" + re.sub(r"\.git$", "", m.group(2))).lower()
            return ALIAS.get(r, r)
    return "maven:" + pkg.split(":")[0].lower()


P = pd.read_csv(ROOT / "outputs/step11/projects.csv")
P = P[P.event == "akka"][["group", "treated", "project", "outcome"]]
want = set(P.project)

# release -> (project, published)
rel = {}
for r in csv.DictReader(open(ROOT / "outputs/step04/project_panel.csv", encoding="utf-8")):
    if r["project"] in want:
        rel[(r["package"], r["version"])] = (r["project"], r["published"][:10])
latest = {}
cv = list(csv.DictReader(open(ROOT / "data/raw/step06/bq_cmp_versions.csv", encoding="utf-8")))
for r in cv:
    if r["source_repo"] and (r["published"] or "") >= latest.get(r["package"], ("", ""))[0]:
        latest[r["package"]] = (r["published"] or "", r["source_repo"])
for r in cv:
    k = (r["package"], r["version"])
    if k in rel or not r["published"]:
        continue
    proj = norm_repo(latest.get(r["package"], ("", ""))[1], r["package"])
    if proj in want:
        rel[k] = (proj, r["published"][:10])

flags = {}
for l in open(ROOT / "data/raw/step12/bq_lightbend_declared.jsonl", encoding="utf-8"):
    j = json.loads(l)
    k = (j["package"], j["version"])
    if k not in rel:
        continue
    f = {s: 0 for s in SETS}
    for d in j["deps"]:
        if (d.get("Scope") or "").lower() == "test":
            continue
        g, a = d["Name"].split(":", 1)
        for s, fn in SETS.items():
            if fn(g, a):
                f[s] = 1
    flags[k] = f
by_proj = defaultdict(list)
for k, (proj, pub) in rel.items():
    if k in flags:
        by_proj[proj].append((pub, flags[k]))
print("releases matched to a BigQuery row:", sum(len(v) for v in by_proj.values()), "of", len(rel))


def measures(rs, a, b, c):
    pre = [f for p, f in rs if a <= p < b]
    post = sorted([(p, f) for p, f in rs if b <= p < c], key=lambda x: x[0])
    out = {}
    for s in SETS:
        u = int(any(f[s] for f in pre)) if pre else None
        if not post or u is None:
            out[s] = (u, None, None)
            continue
        last = post[-1][0]
        ret = int(any(f[s] for p, f in post if p == last)) if u else None
        adp = int(any(f[s] for p, f in post)) if not u else None
        out[s] = (u, ret, adp)
    return out


def d(x):
    return x.isoformat()


WIN = {"main": (d(E - timedelta(days=365)), d(E), d(E + timedelta(days=730))),
       "placebo": (d(E - timedelta(days=1095)), d(E - timedelta(days=730)), d(E))}
rows = []
for _, pr in P.iterrows():
    rs = by_proj.get(pr.project, [])
    for w, (a, b, c) in WIN.items():
        for s, (u, ret, adp) in measures(rs, a, b, c).items():
            rows.append(dict(project=pr.project, group=pr.group, outcome=pr.outcome, window=w, set=s,
                             user_pre=u, retained=ret, adopted=adp))
D = pd.DataFrame(rows)
D.to_csv(O / "spillover_projects.csv", index=False)


def tab(df, col):
    g = df[df[col].notna()]
    t = g[g.group == "akka"][col]
    cmp = g[g.group == "cmp"][col]
    res = dict(akka=f"{int(t.sum())}/{len(t)}", cmp=f"{int(cmp.sum())}/{len(cmp)}",
               akka_share=round(t.mean(), 3) if len(t) else None, cmp_share=round(cmp.mean(), 3) if len(cmp) else None)
    if len(t) and len(cmp):
        res["fisher_p"] = round(float(fisher_exact([[t.sum(), len(t) - t.sum()], [cmp.sum(), len(cmp) - cmp.sum()]])[1]), 4)
    return res


out = {"event": d(E), "windows": WIN, "matched_releases": int(sum(len(v) for v in by_proj.values()))}
for w in WIN:
    for s in SETS:
        g = D[(D.window == w) & (D.set == s)]
        out.setdefault(w, {})[s] = dict(users_pre=tab(g, "user_pre"), retained=tab(g, "retained"),
                                        adopted=tab(g, "adopted"))
# retention of S_core among treated Akka dependents, by Step 11 outcome
g = D[(D.window == "main") & (D.set == "S_core") & (D.group == "akka") & D.retained.notna()]
out["main_S_core_retention_by_outcome"] = {o: f"{int(x.retained.sum())}/{len(x)}" for o, x in g.groupby("outcome")}
(O / "spillover.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
