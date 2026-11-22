"""Step 9d: build definitions of the Elasticsearch validation sample, independently of the registry.

Reuses the step05b procedure unchanged (commit-only partial clone, default-branch commit as of the last
release on or before the horizon, maintained branches within 183 days, build files and README), with:
  horizon : branch states as of 2024-11-11 (step05b's 2025-10-01 cutoff is overridden)
  sample  : outputs/step09/validation_sample.csv (last_release_by_horizon is on or before 2024-11-11)
  storage : data/raw/step09/build_files/<owner>__<repo>/<ref>/...
  excerpt : lines mentioning elasticsearch/opensearch/elastic clients, shading, spring-boot parents/BOMs
Windows cannot hold refs that differ only in case; for repositories where the full fetch failed on such
refs (LOCKFIX), the clone is pre-created from an explicit branch list without bot/feature/bugfix branches
(which the codebook ignores anyway) and without case-duplicates.
Usage: python -I scripts/step09d_build_files.py --scratch <dir> [--workers 4] [--only repo1,repo2]
"""
import argparse
import csv
import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import step05b_build_files as b  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
b.RAW = ROOT / "data" / "raw" / "step09" / "build_files"
_git = b.git


def _git_es(d, *args, **kw):
    """step05b checks maintained branches as of 2025-10-01 (Akka horizon); Elasticsearch uses 2024-11-11."""
    return _git(d, *("--before=2024-11-12" if x == "--before=2025-10-01" else x for x in args), **kw)


b.git = _git_es
b.HIT = re.compile(r"elastic|opensearch|shade|relocat|spring-boot-(starter-)?parent|spring-boot-dependencies|"
                   r"<parent>|<artifactId>[^<]*-parent<|\bbom\b|platform\(", re.I)


LOCKFIX = {"github.com/vertigo-io/vertigo-connectors", "github.com/epam/indigo", "github.com/annot8/annot8-components"}


def preclone(row, scratch):
    owner, repo = row["repo"].split("/")[1:3]
    d = Path(scratch) / f"{owner}__{repo}"
    if d.exists():
        import os
        import shutil
        import stat

        def _rw(fn, path, _):  # git pack files are read-only on Windows
            os.chmod(path, stat.S_IWRITE)
            fn(path)
        shutil.rmtree(d, onerror=_rw)
    subprocess.run(["git", "init", "-q", "--bare", str(d)], check=True)
    b.git(d, "remote", "add", "origin", f"https://github.com/{owner}/{repo}.git")
    b.git(d, "config", "remote.origin.promisor", "true")
    b.git(d, "config", "remote.origin.partialclonefilter", "blob:none")
    heads = [l.split("	")[1][len("refs/heads/"):] for l in b.git(d, "ls-remote", "--heads", "origin").splitlines()]
    seen, keep = set(), []
    for h in heads:  # drop bot/feature branches and case-duplicates (Windows refs are case-insensitive)
        if b.BOT.search(h) or re.match(r"(feature|bugfix|hotfix|fix)/", h, re.I) or h.lower() in seen:
            continue
        seen.add(h.lower())
        keep.append(f"+refs/heads/{h}:refs/remotes/origin/{h}")
    b.git(d, "fetch", "-q", "--no-tags", "--filter=tree:0", "origin", *keep, timeout=1800)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    rows = [r for r in csv.DictReader(open(ROOT / "outputs/step09/validation_sample.csv", encoding="utf-8"))
            if r.get("available", "1") == "1"]
    if a.only:
        rows = [r for r in rows if r["repo"] in a.only.split(",")]
    for r in rows:
        if r["repo"] in LOCKFIX:
            preclone(r, a.scratch)
    with ThreadPoolExecutor(a.workers) as ex:
        res = list(ex.map(lambda r: b.one(r, a.scratch), rows))
    b.RAW.mkdir(parents=True, exist_ok=True)
    man = b.RAW / "manifest.json"
    old = {x["project"]: x for x in json.loads(man.read_text())} if man.exists() and a.only else {}
    old.update({x["project"]: x for x in res})
    man.write_text(json.dumps(list(old.values()), indent=1))
    print("errors:", [(x["project"], x["error"][:100]) for x in old.values() if "error" in x])


if __name__ == "__main__":
    main()
