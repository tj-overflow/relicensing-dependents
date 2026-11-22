"""Step 5b: fetch build definitions from each sampled repository, independently of the registry.

For each project in outputs/step05/validation_sample.csv:
  1. commit-only partial clone (git, no API) into a scratch directory;
  2. default-branch commit as of the project's last release on or before 2025-09-30 (+1 day);
  3. other branches whose last commit before 2025-10-01 falls within 183 days before that release
     (candidate maintained lines, for the 'dual' check), excluding bot branches;
  4. build files at each commit (sbt, project/*.scala, Maven, Gradle, Mill) and the root README.
Saves files under data/raw/step05/build_files/<owner>__<repo>/<ref>/..., a manifest with SHA-256,
and a compact report of lines mentioning akka/pekko/shading for the hand-coding step.
The report deliberately omits the registry outcome.
Usage: python -I scripts/step05b_build_files.py --scratch <dir> [--workers 4]
"""
import argparse
import csv
import datetime as dt
import hashlib
import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "step05" / "build_files"
BUILD = re.compile(r"(^|/)(build\.sbt|[^/]+\.sbt|build\.sc|pom\.xml|build\.gradle(\.kts)?|settings\.gradle(\.kts)?|"
                   r"libs\.versions\.toml|gradle\.properties|[^/]*[Dd]ependenc[^/]*\.scala|[^/]*[Vv]ersions?\.scala|"
                   r"[^/]*Build\.scala|[^/]*Settings\.scala)$|(^|/)project/[^/]+\.scala$")
SKIP = re.compile(r"(^|/)(src/test|src/it|test-?data|testdata|docs?|examples?|samples?|benchmarks?|\.github)/", re.I)
BOT = re.compile(r"^(dependabot|renovate|update/|scala-steward|snyk|gh-pages|pr/|revert-)", re.I)
HIT = re.compile(r"akka|pekko|shade|relocat|assembly|crossScalaVersions", re.I)


def git(d, *args, check=True, timeout=900):
    r = subprocess.run(["git", "-C", str(d), *args], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout)
    if check and r.returncode:
        raise RuntimeError(f"git {' '.join(args[:3])}: {r.stderr.strip()[:300]}")
    return r.stdout


def files_at(d, rev):
    paths = git(d, "ls-tree", "-r", "--name-only", rev).splitlines()
    return [p for p in paths if BUILD.search(p) and not SKIP.search(p) and "/target/" not in p], paths


def save(d, rev, paths, dest):
    out = []
    for p in paths:
        try:
            txt = git(d, "show", f"{rev}:{p}", timeout=300)
        except Exception as e:
            out.append(dict(path=p, error=str(e)[:200]))
            continue
        f = dest / p
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(txt, encoding="utf-8")
        hits = [f"{i + 1}: {l.strip()[:220]}" for i, l in enumerate(txt.splitlines()) if HIT.search(l)]
        out.append(dict(path=p, sha256=hashlib.sha256(txt.encode()).hexdigest(), hits=hits))
    return out


def one(row, scratch):
    owner, repo = row["repo"].split("/")[1:3]
    key = f"{owner}__{repo}"
    d = Path(scratch) / key
    url = f"https://github.com/{owner}/{repo}.git"
    res = dict(project=row["project"], repo=row["repo"], key=key, refs=[])
    try:
        if not (d / "HEAD").exists():
            subprocess.run(["git", "init", "-q", "--bare", str(d)], check=True)
            git(d, "remote", "add", "origin", url)
            git(d, "config", "remote.origin.promisor", "true")
            git(d, "config", "remote.origin.partialclonefilter", "blob:none")
            git(d, "fetch", "-q", "--no-tags", "--filter=tree:0", "origin",
                "+refs/heads/*:refs/remotes/origin/*", timeout=1800)
        head = git(d, "ls-remote", "--symref", "origin", "HEAD").splitlines()[0]
        default = re.search(r"refs/heads/(\S+)", head).group(1)
        rel = dt.date.fromisoformat(row["last_release_by_horizon"])
        before = (rel + dt.timedelta(days=1)).isoformat()
        rev = git(d, "rev-list", "-1", f"--before={before}", f"origin/{default}").strip()
        targets = [("default@" + default, rev)]
        lo = (rel - dt.timedelta(days=183)).isoformat()
        cands = []
        for b in git(d, "for-each-ref", "--format=%(refname)", "refs/remotes/origin").split():
            name = b[len("refs/remotes/origin/"):]
            if name in (default, "HEAD") or BOT.search(name):
                continue
            r2 = git(d, "rev-list", "-1", "--before=2025-10-01", b, check=False).strip()
            if not r2:
                continue
            cdate = git(d, "show", "-s", "--format=%cs", r2).strip()
            if cdate >= lo:
                cands.append((cdate, name, r2))
        for cdate, name, r2 in sorted(cands, reverse=True)[:6]:
            targets.append((f"branch@{name}@{cdate}", r2))
        for label, r in targets:
            paths, allp = files_at(d, r)
            if len(paths) > 400:
                paths = [p for p in paths if p.count("/") <= 2 or not p.endswith("pom.xml")][:400]
            dest = RAW / key / re.sub(r"[^\w.@-]", "_", label)
            ent = dict(label=label, commit=r, date=git(d, "show", "-s", "--format=%cs", r).strip(),
                       n_build_files=len(paths), files=save(d, r, paths, dest))
            if label.startswith("default"):
                readme = [p for p in allp if re.fullmatch(r"README(\.\w+)?", p, re.I)]
                ent["readme"] = save(d, r, readme[:1], dest)
            res["refs"].append(ent)
        res["default_branch"] = default
    except Exception as e:
        import traceback
        res["error"] = (str(e) + " | " + traceback.format_exc().splitlines()[-3])[:500]
    print(key, "ok" if "error" not in res else res["error"][:120], flush=True)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    rows = list(csv.DictReader(open(ROOT / "outputs/step05/validation_sample.csv", encoding="utf-8")))
    if a.only:
        rows = [r for r in rows if a.only in r["repo"]]
    with ThreadPoolExecutor(a.workers) as ex:
        res = list(ex.map(lambda r: one(r, a.scratch), rows))
    RAW.mkdir(parents=True, exist_ok=True)
    man = RAW / "manifest.json"
    old = {x["project"]: x for x in json.loads(man.read_text())} if man.exists() and a.only else {}
    old.update({x["project"]: x for x in res})
    man.write_text(json.dumps(list(old.values()), indent=1))
    print("errors:", [x["project"] for x in old.values() if "error" in x])


if __name__ == "__main__":
    main()
