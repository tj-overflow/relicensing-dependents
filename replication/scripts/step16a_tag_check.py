"""Step 16a: do projects coded as inactive or frozen have later version tags in their own repositories?

Threat checked (paper, Section 8): a project that moved its publishing off Maven Central, or that moved to new
artifacts declaring neither Akka nor Pekko, would look inactive (no_release) or frozen in the registry data.

Method. For every non-vendor Akka risk-set project on GitHub with outcome_v2 in {no_release, freeze}, list the
repository's tags with `git ls-remote --tags` (standard git protocol, no API, no credentials), sequentially at
1 request per second. A tag counts as a stable version tag if it contains a numeric version (x.y or x.y.z) and no
pre-release marker. The project is flagged if its highest stable tag is above the highest version of its risk-set
artifacts on Maven Central (from akka_release_status), that is, it tagged a later release that is not in the data.
Tags carry no dates, so a flag means "a later version exists in the repository", not when it was made.

Inputs:  outputs/step05/risk_set_v2.csv, outputs/step04/project_panel.csv (the same data as the dataset tables)
Outputs: data/raw/step16/tags.json (raw ls-remote tag names per repository)
         outputs/step16/tag_check.csv, outputs/step16/tag_check.json
Usage:   python scripts/step16a_tag_check.py [--offline]   (--offline reuses data/raw/step16/tags.json)
"""
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/step16"
OUT = ROOT / "outputs/step16"
RAW.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)

dep = pd.read_csv(ROOT / "outputs/step05/risk_set_v2.csv", usecols=["project", "vendor", "outcome_v2"])
dep = dep[(dep.vendor == 0) & dep.outcome_v2.isin(["no_release", "freeze"]) & dep.project.str.startswith("github.com/")]
rel = pd.read_csv(ROOT / "outputs/step04/project_panel.csv", usecols=["project", "version", "published"])

PRE = re.compile(r"(snapshot|alpha|beta|rc|\bm\d|-m\d|milestone|preview|dev|pre)", re.I)
NUM = re.compile(r"(\d+(?:\.\d+){1,3})")


def vtuple(s):
    m = NUM.search(str(s))
    if not m or PRE.search(str(s)):
        return None
    return tuple(int(x) for x in m.group(1).split("."))


def pad(t):
    return tuple(list(t) + [0] * (4 - len(t)))


cache_path = RAW / "tags.json"
cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
offline = "--offline" in sys.argv
for i, p in enumerate(dep.project):
    if p in cache or offline:
        continue
    url = "https://" + p
    try:
        r = subprocess.run(["git", "ls-remote", "--tags", url], capture_output=True, text=True, timeout=60,
                           env={**__import__("os").environ, "GIT_TERMINAL_PROMPT": "0"})
        if r.returncode == 0:
            cache[p] = {"ok": True, "tags": sorted({ln.split("refs/tags/")[1].removesuffix("^{}")
                                                     for ln in r.stdout.splitlines() if "refs/tags/" in ln})}
        else:
            cache[p] = {"ok": False, "error": r.stderr.strip()[:200]}
    except subprocess.TimeoutExpired:
        cache[p] = {"ok": False, "error": "timeout"}
    if i % 25 == 0:
        cache_path.write_text(json.dumps(cache, indent=0), encoding="utf-8")
        print(i, "of", len(dep), flush=True)
    time.sleep(1)
cache_path.write_text(json.dumps(cache, indent=0), encoding="utf-8")

rows = []
for _, d in dep.iterrows():
    p = d.project
    c = cache.get(p, {"ok": False, "error": "not fetched"})
    mv = [t for t in (vtuple(v) for v in rel.loc[rel.project == p, "version"]) if t]
    maven_max = max(mv, key=pad) if mv else None
    last_pub = rel.loc[rel.project == p, "published"].max()
    tv = [(t, vtuple(t)) for t in c.get("tags", [])]
    tv = [(t, v) for t, v in tv if v]
    later = [t for t, v in tv if maven_max and pad(v) > pad(maven_max)] if c.get("ok") else []
    top = max(tv, key=lambda x: pad(x[1]))[0] if tv else ""
    rows.append(dict(project=p, outcome_v2=d.outcome_v2, repo_ok=int(bool(c.get("ok"))), n_tags=len(c.get("tags", [])),
                     n_version_tags=len(tv), maven_max=".".join(map(str, maven_max)) if maven_max else "",
                     maven_last_published=last_pub, top_tag=top, n_later_tags=len(later),
                     later_tags=";".join(sorted(later, key=lambda t: pad(vtuple(t)))[-5:]),
                     flagged=int(len(later) > 0)))
t = pd.DataFrame(rows)
t.to_csv(OUT / "tag_check.csv", index=False)
summ = {}
for oc, g in t.groupby("outcome_v2"):
    ok = g[g.repo_ok == 1]
    summ[oc] = dict(projects=len(g), repo_reachable=len(ok), with_version_tags=int((ok.n_version_tags > 0).sum()),
                    flagged_later_tag=int(ok.flagged.sum()))
summ["all"] = dict(projects=len(t), repo_reachable=int(t.repo_ok.sum()),
                   with_version_tags=int(((t.repo_ok == 1) & (t.n_version_tags > 0)).sum()),
                   flagged_later_tag=int(t.flagged.sum()))
(OUT / "tag_check.json").write_text(json.dumps(summ, indent=1), encoding="utf-8")
print(json.dumps(summ, indent=1))
