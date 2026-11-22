"""Step 11z: GitHub owner type (A1 exposure proxy) for every owner in the Akka non-vendor risk set.

Coding rule: A1 = 1 if type == "Organization"; foundation owners
(apache, eclipse, eclipse-ditto, ...) form their own category through risk_set_v2's `foundation` column.
Endpoint: GET https://api.github.com/users/{owner} (documented REST API), unauthenticated, at most one
request per 61 seconds (the unauthenticated limit is 60 per hour). Cached; existing Step 5 records reused.
Output: data/raw/step11/owners.json (merged with data/raw/step05/owners.json)
"""
import csv
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/raw/step11/owners.json"
OUT.parent.mkdir(parents=True, exist_ok=True)
KEEP = ("login", "type", "name", "company", "blog", "bio", "location", "created_at", "public_repos", "followers")

have = {k.lower(): v for k, v in json.loads((ROOT / "data/raw/step05/owners.json").read_text(encoding="utf-8")).items()}
if OUT.exists():
    have.update({k.lower(): v for k, v in json.loads(OUT.read_text(encoding="utf-8")).items()})
rs = [x for x in csv.DictReader(open(ROOT / "outputs/step05/risk_set_v2.csv", encoding="utf-8")) if x["vendor"] == "0"]
owners = sorted({x["project"].split("/")[1].lower() for x in rs if x["project"].startswith("github.com/")})
todo = [o for o in owners if o not in have]
print("owners", len(owners), "to fetch", len(todo), flush=True)
def get(o):
    """One owner record; waits for the quota reset on 403/429 and retries."""
    while True:
        req = urllib.request.Request(f"https://api.github.com/users/{o}",
                                     headers={"User-Agent": "research-script/1.0", "Accept": "application/vnd.github+json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                j = json.load(r)
                return {k: j.get(k) for k in KEEP}, r.headers.get("X-RateLimit-Remaining")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {"login": o, "type": "not_found"}, None
            if e.code in (403, 429):
                reset = int(e.headers.get("X-RateLimit-Reset", time.time() + 3600))
                print("rate limited; sleeping until reset", flush=True)
                time.sleep(max(60, reset - time.time() + 30))
                continue
            print("error", o, e.code, flush=True)
            return {"login": o, "type": f"error_{e.code}"}, None
        except Exception as e:  # network error: wait and retry
            print("network", o, repr(e)[:80], flush=True)
            time.sleep(120)


for i, o in enumerate(todo, 1):
    have[o], rem = get(o)
    OUT.write_text(json.dumps(have, indent=1))
    if i % 20 == 0:
        print(i, "remaining quota", rem, flush=True)
    time.sleep(61)
types = {}
for o in owners:
    t = have.get(o, {}).get("type", "missing")
    types[t] = types.get(t, 0) + 1
print("done", types, flush=True)
