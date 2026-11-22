"""Step 4a: discover candidate downstream dependents of Apache-era Akka.

1. Lists all artifacts in the Akka groups (ecosyste.ms namespace listing; Maven Central coordinates).
2. Keeps Scala-suffixed artifacts (_2.11, _2.12, _2.13, _3).
3. For each artifact, takes versions published 2018-01-01 .. 2022-09-08 (deps.dev API).
4. For each (artifact, version), queries the deps.dev web endpoint for direct dependents
   (returns a sample capped at 100 per version, plus exact counts).
5. Writes every (dependent package, dependent version, akka artifact, akka version) edge, and a
   per-version truncation log.

Outputs: data/raw/step04/akka_artifacts.json, data/raw/step04/dependent_edges.csv,
         data/raw/step04/version_counts.csv
Usage: python -I scripts/step04a_candidate_dependents.py   (resumable)
"""
import csv
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "step04"
OUT.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "research-script/1.0"}
GROUPS = ["com.typesafe.akka", "com.lightbend.akka", "com.lightbend.akka.grpc",
          "com.lightbend.akka.management", "com.lightbend.akka.discovery"]
SUFFIXES = ("_2.11", "_2.12", "_2.13", "_3")
VMIN, VMAX = "2018-01-01", "2022-09-08"


def get(url, tries=5):
    for a in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(3 * (a + 1))
        except Exception:
            time.sleep(3 * (a + 1))
    return None


# 1-2. artifact list
art_file = OUT / "akka_artifacts.json"
if art_file.exists():
    artifacts = json.loads(art_file.read_text())
else:
    artifacts = []
    for g in GROUPS:
        page = 1
        while True:
            d = get(f"https://packages.ecosyste.ms/api/v1/registries/repo1.maven.org/namespaces/{g}/packages?per_page=1000&page={page}")
            if not d:
                break
            artifacts += [p["name"] for p in d if p["name"].endswith(SUFFIXES)]
            if len(d) < 1000:
                break
            page += 1
    artifacts = sorted(set(artifacts))
    art_file.write_text(json.dumps(artifacts, indent=0))
print("artifacts:", len(artifacts))

# 3-4. versions and dependents (resumable)
done = set()
edges_path, counts_path = OUT / "dependent_edges.csv", OUT / "version_counts.csv"
if counts_path.exists():
    with open(counts_path, encoding="utf-8") as f:
        done = {(r["akka_artifact"], r["akka_version"]) for r in csv.DictReader(f)}
new_files = not counts_path.exists()
fe = open(edges_path, "a", newline="", encoding="utf-8")
fc = open(counts_path, "a", newline="", encoding="utf-8")
we = csv.writer(fe)
wc = csv.writer(fc)
if new_files:
    we.writerow(["dependent", "dependent_version", "akka_artifact", "akka_version"])
    wc.writerow(["akka_artifact", "akka_version", "published", "direct_count", "sample_n", "truncated"])

for i, art in enumerate(artifacts):
    pkg = get("https://api.deps.dev/v3/systems/maven/packages/" + urllib.parse.quote(art, safe=""))
    if not pkg:
        continue
    vers = [(v["versionKey"]["version"], v.get("publishedAt", "")) for v in pkg.get("versions", [])]
    vers = [v for v in vers if VMIN <= (v[1] or "")[:10] <= VMAX]
    for ver, pub in vers:
        if (art, ver) in done:
            continue
        d = get("https://deps.dev/_/s/maven/p/" + urllib.parse.quote(art, safe="") + "/v/" + urllib.parse.quote(ver, safe="") + "/dependents")
        if d is None:
            wc.writerow([art, ver, pub[:10], "NA", 0, ""])
            continue
        sample = d.get("directSample") or []
        for s in sample:
            we.writerow([s["package"]["name"], s.get("version", ""), art, ver])
        dc = d.get("directCount") or 0
        wc.writerow([art, ver, pub[:10], dc, len(sample), int(dc > len(sample))])
        time.sleep(0.15)
    fe.flush()
    fc.flush()
    if i % 20 == 0:
        print(f"{i+1}/{len(artifacts)} {art}", flush=True)
fe.close()
fc.close()
print("done")
