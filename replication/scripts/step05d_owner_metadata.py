"""Step 5d: GitHub owner metadata (type, name, company, blog, bio) for given owners.

Uses the documented REST endpoint GET /users/{owner}. Unauthenticated limit is 60 requests per
hour; a token in GH_TOKEN is used if present. Cached in data/raw/step05/owners.json.
Usage: python -I scripts/step05d_owner_metadata.py [--sample-only]
"""
import csv
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "raw" / "step05" / "owners.json"
cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
if "--sample-only" in sys.argv:
    owners = {r["repo"].split("/")[1] for r in csv.DictReader(open(ROOT / "outputs/step05/validation_sample.csv"))}
else:
    owners = {r["owner"] for r in csv.DictReader(open(ROOT / "outputs/step05/project_flags.csv"))
              if r["active_post"] == "1" and not r["owner"].startswith("maven:")}
hdr = {"Accept": "application/vnd.github+json", "User-Agent": "supplier-relicensing-research"}
if os.environ.get("GH_TOKEN"):
    hdr["Authorization"] = "Bearer " + os.environ["GH_TOKEN"]
for o in sorted(owners - set(cache)):
    try:
        with urllib.request.urlopen(urllib.request.Request(f"https://api.github.com/users/{o}", headers=hdr), timeout=30) as r:
            j = json.load(r)
            left = r.headers.get("X-RateLimit-Remaining")
        cache[o] = {k: j.get(k) for k in ("login", "type", "name", "company", "blog", "bio", "location", "created_at",
                                          "public_repos", "followers")}
        print(o, j.get("type"), left, flush=True)
    except urllib.error.HTTPError as e:
        print(o, "HTTP", e.code, flush=True)
        if e.code in (403, 429):
            break
        cache[o] = {"login": o, "error": e.code}
    time.sleep(0.5)
CACHE.write_text(json.dumps(cache, indent=1))
print("cached", len(cache), "missing", len(owners - set(cache)))
