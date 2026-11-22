"""Step 15e (R4): offline lists between the BigQuery stages of step15d. No network access.

  exposure-packages : packages of the Akka A24-A27 risk-set projects (from data/raw/step04/releases.csv, repos
                      normalised as in step13g) and of the Elasticsearch risk-set projects
                      (outputs/step08/es_project_panel.csv) -> outputs/step15/r4_exposure_packages.json
  candidates        : applies benchmark selection rules 1-3 to data/raw/step15/candidates.csv:
                      exclusions by group and base name, a stable x.y.0 (y >= 1) in BOTH windows; launch = first
                      such release in each window -> outputs/step15/r4_candidates.json ("libraries")
  extract           : keeps the 20 libraries with the most dependent packages (data/raw/step15/counts.csv) for the
                      dependents extraction -> adds "extract" to r4_candidates.json. The 30-active rule and the
                      top-5 selection by early risk set are applied later (step15f).
Usage: python -I scripts/step15e_r4_lists.py <exposure-packages|candidates|extract>
"""
import csv
import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
O = ROOT / "outputs/step15"
RAW = ROOT / "data/raw/step15"
SFX = re.compile(r"_(2\.1[0-3]|3)$")
EXCL_GROUP = ("com.typesafe.akka", "com.lightbend", "org.apache.pekko", "co.fs2", "dev.zio", "io.monix",
              "org.http4s", "com.softwaremill.sttp", "com.typesafe.play", "org.playframework", "com.twitter",
              "io.vertx", "org.scalatra")
EXCL_WORD = ("http", "stream", "actor", "effect")
W1 = ("2019-05-06", "2020-05-07")
W2 = ("2022-04-19", "2023-04-20")


def exposure_packages():
    head = (ROOT / "scripts/step13g_lu_build.py").read_text(encoding="utf-8").split("\ncore, avail = set()")[0]
    ns = {"__file__": str(ROOT / "scripts/step13g_lu_build.py")}
    exec(head, ns)
    norm_repo = ns["norm_repo"]
    lu = pd.concat([pd.read_csv(ROOT / "outputs/step13/lu/cohorts.csv"),
                    pd.read_csv(ROOT / "outputs/step13/lu/cohorts_a24.csv")])
    akka_proj = set(lu.loc[lu.group == "akka", "project"])
    repo = {}
    for r in csv.DictReader(open(ROOT / "data/raw/step04/releases.csv", encoding="utf-8")):
        if r["scm"]:
            repo[r["package"]] = r["scm"]
    # packages without an scm link are grouped by group id (norm_repo fallback)
    allpk = {r["package"] for r in csv.DictReader(open(ROOT / "data/raw/step04/releases.csv", encoding="utf-8"))}
    pk_akka = sorted({p for p in allpk if norm_repo(repo.get(p), p) in akka_proj})
    es = pd.read_csv(ROOT / "outputs/step08/es_project_panel.csv", usecols=["project", "package"])
    esr = pd.read_csv(ROOT / "outputs/step08/es_risk_set.csv", usecols=["project"])
    pk_es = sorted(set(es.loc[es.project.isin(esr.project), "package"]))
    out = dict(packages=sorted(set(pk_akka) | set(pk_es)), n_akka_projects=len(akka_proj),
               n_akka_packages=len(pk_akka), n_es_packages=len(pk_es))
    (O / "r4_exposure_packages.json").write_text(json.dumps(out, indent=1))
    print({k: v for k, v in out.items() if k != "packages"}, "total", len(out["packages"]))


def candidates():
    d = pd.read_csv(RAW / "candidates.csv" if (RAW / "candidates.csv").exists() else RAW / "candidates.csv.gz")
    d["published"] = d.published.astype(str).str[:10]
    d["library"] = d.package.str.replace(SFX, "", regex=True)
    d["group"] = d.library.str.split(":").str[0]
    d["base"] = d.library.str.split(":").str[1]
    ex_g = d.group.apply(lambda g: any(g.startswith(e) for e in EXCL_GROUP))
    ex_tl = (d.group == "org.typelevel") & d.base.str.startswith("cats-effect")
    ex_w = d.base.str.lower().apply(lambda b: any(w in b for w in EXCL_WORD))
    kept = d[~(ex_g | ex_tl | ex_w)].copy()
    kept["win"] = kept.published.apply(lambda p: 1 if W1[0] <= p < W1[1] else (2 if W2[0] <= p < W2[1] else 0))
    first = kept[kept.win > 0].sort_values("published").groupby(["library", "win"]).first().reset_index()
    both = first.pivot(index="library", columns="win", values=["version", "published"]).dropna()
    libs = []
    for lib, r in both.iterrows():
        libs.append(dict(library=lib, early_version=r[("version", 1)], early_launch=r[("published", 1)],
                         late_version=r[("version", 2)], late_launch=r[("published", 2)]))
    out = dict(rule="benchmark selection rules 1-3", n_rows=len(d), n_excluded=int((ex_g | ex_tl | ex_w).sum()),
               libraries=[x["library"] for x in libs], launches=libs)
    (O / "r4_candidates.json").write_text(json.dumps(out, indent=1))
    print(len(libs), "libraries with a minor launch in both windows")


def extract():
    f = O / "r4_candidates.json"
    c = json.loads(f.read_text())
    n = pd.read_csv(RAW / "counts.csv").sort_values("dependents", ascending=False)
    n = n[n.library.isin(c["libraries"])]
    c["extract"] = n.head(20).library.tolist()
    c["extract_counts"] = dict(zip(n.head(20).library, n.head(20).dependents.astype(int)))
    f.write_text(json.dumps(c, indent=1))
    print(c["extract_counts"])


if __name__ == "__main__":
    {"exposure-packages": exposure_packages, "candidates": candidates, "extract": extract}[sys.argv[1]]()
