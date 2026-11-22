"""Step 12z: issues and pull requests that mention the relicensing, in treated projects' own repositories.

Corpus for the Step 12 motive coding.
Endpoint: GET https://api.github.com/search/issues (documented REST API), unauthenticated, one request per
7 seconds (the unauthenticated search limit is 10 per minute). Title and body only (comments are not returned
by search, and fetching them would need the 60-per-hour core quota).
Queries:
  Akka:          repo:{o/n} pekko OR license OR licence OR BSL OR lightbend in:title,body created:>=2022-06-01
  Elasticsearch: repo:{o/n} opensearch OR license OR licence OR SSPL OR ELv2 in:title,body created:>=2020-10-01
Up to 100 hits per repository (first page, oldest first); the total count is kept so truncation is visible.
Cache: one JSON file per repository; reruns skip cached repositories. Aborts after 3 consecutive failures
that are not rate-limit waits.
Output: data/raw/step12/issues/{event}__{owner}__{name}.json
"""
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/raw/step12/issues"
OUT.mkdir(parents=True, exist_ok=True)
Q = {"akka": "pekko OR license OR licence OR BSL OR lightbend in:title,body created:>=2022-06-01",
     "es": "opensearch OR license OR licence OR SSPL OR ELv2 in:title,body created:>=2020-10-01"}
KEEP = ("number", "title", "state", "created_at", "closed_at", "html_url", "author_association", "comments")

pj = pd.read_csv(ROOT / "outputs/step11/projects.csv")
t = pj[(pj.treated == 1) & pj.project.str.startswith("github.com/")]
todo = []
for ev, p in zip(t.event, t.project):
    o, n = p.split("/")[1:3]
    f = OUT / f"{ev}__{o}__{n}.json"
    if not f.exists():
        todo.append((ev, o, n, f))
print("repositories", len(t), "to fetch", len(todo), flush=True)

fails = 0
for i, (ev, o, n, f) in enumerate(todo, 1):
    q = f"repo:{o}/{n} {Q[ev]}"
    url = "https://api.github.com/search/issues?" + urllib.parse.urlencode(
        {"q": q, "per_page": 100, "sort": "created", "order": "asc"})
    req = urllib.request.Request(url, headers={"User-Agent": "research-script/1.0",
                                               "Accept": "application/vnd.github+json"})
    while True:
        time.sleep(7.0)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                j = json.load(r)
            items = [{**{k: it.get(k) for k in KEEP}, "is_pr": "pull_request" in it,
                      "user": (it.get("user") or {}).get("login"), "body": (it.get("body") or "")[:4000]}
                     for it in j.get("items", [])]
            rec = dict(event=ev, repo=f"{o}/{n}", query=q, total_count=j.get("total_count"),
                       incomplete=j.get("incomplete_results"), items=items)
            fails = 0
            break
        except urllib.error.HTTPError as e:
            if e.code in (403, 429):
                reset = int(e.headers.get("X-RateLimit-Reset") or time.time() + 60)
                wait = max(reset - time.time(), 0) + 5
                print(f"rate limit, waiting {wait:.0f}s", flush=True)
                time.sleep(wait)
                continue
            if e.code == 422:  # repository missing, renamed or private
                rec = dict(event=ev, repo=f"{o}/{n}", query=q, total_count=None, error=422, items=[])
                break
            fails += 1
            print("http", e.code, o, n, flush=True)
            if fails >= 3:
                sys.exit(3)
            continue
        except (urllib.error.URLError, TimeoutError) as e:
            fails += 1
            print("net", e, o, n, flush=True)
            if fails >= 3:
                sys.exit(3)
            continue
    f.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    if i % 25 == 0:
        print(i, "done", flush=True)
print("finished", flush=True)
