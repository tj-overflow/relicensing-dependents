"""Step 3: release calendar and licences for Akka and Pekko modules from the deps.dev API.

For each Maven package, retrieves all versions with publication dates, then the
declared licence of selected versions (first release overall, the last 2.6.x/
Apache-era release and the first BSL-era release for Akka; first release for Pekko).

Output: outputs/step03/release_calendar.csv and outputs/step03/package_versions.json
Usage: python -I scripts/step03_release_calendar.py
"""
import csv
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "step03"
OUT.mkdir(parents=True, exist_ok=True)
API = "https://api.deps.dev/v3/systems/maven/packages/"

# (family, module label, package name for Scala 2.13, alternative names to probe)
AKKA = [
    ("akka", "actor", "com.typesafe.akka:akka-actor_2.13"),
    ("akka", "stream", "com.typesafe.akka:akka-stream_2.13"),
    ("akka", "cluster", "com.typesafe.akka:akka-cluster_2.13"),
    ("akka", "persistence", "com.typesafe.akka:akka-persistence_2.13"),
    ("akka", "http", "com.typesafe.akka:akka-http_2.13"),
    ("akka", "grpc", "com.lightbend.akka.grpc:akka-grpc-runtime_2.13"),
    ("akka", "management", "com.lightbend.akka.management:akka-management_2.13"),
    ("akka", "connectors-kafka", "com.typesafe.akka:akka-stream-kafka_2.13"),
    ("akka", "connectors (alpakka s3)", "com.lightbend.akka:akka-stream-alpakka-s3_2.13"),
    ("akka", "persistence-jdbc", "com.lightbend.akka:akka-persistence-jdbc_2.13"),
    ("akka", "persistence-cassandra", "com.typesafe.akka:akka-persistence-cassandra_2.13"),
    ("akka", "projection", "com.lightbend.akka:akka-projection-core_2.13"),
    ("akka", "actor (Scala 3)", "com.typesafe.akka:akka-actor_3"),
    ("akka", "http (Scala 3)", "com.typesafe.akka:akka-http_3"),
]
PEKKO = [
    ("pekko", "actor", "org.apache.pekko:pekko-actor_2.13"),
    ("pekko", "stream", "org.apache.pekko:pekko-stream_2.13"),
    ("pekko", "cluster", "org.apache.pekko:pekko-cluster_2.13"),
    ("pekko", "persistence", "org.apache.pekko:pekko-persistence_2.13"),
    ("pekko", "http", "org.apache.pekko:pekko-http_2.13"),
    ("pekko", "grpc", "org.apache.pekko:pekko-grpc-runtime_2.13"),
    ("pekko", "management", "org.apache.pekko:pekko-management_2.13"),
    ("pekko", "connectors-kafka", "org.apache.pekko:pekko-connectors-kafka_2.13"),
    ("pekko", "connectors (s3)", "org.apache.pekko:pekko-connectors-s3_2.13"),
    ("pekko", "persistence-jdbc", "org.apache.pekko:pekko-persistence-jdbc_2.13"),
    ("pekko", "persistence-cassandra", "org.apache.pekko:pekko-persistence-cassandra_2.13"),
    ("pekko", "projection", "org.apache.pekko:pekko-projection-core_2.13"),
    ("pekko", "actor (Scala 3)", "org.apache.pekko:pekko-actor_3"),
    ("pekko", "http (Scala 3)", "org.apache.pekko:pekko-http_3"),
]
PLAY = [
    ("play", "play (Akka line)", "com.typesafe.play:play_2.13"),
    ("play", "play (Pekko line)", "org.playframework:play_2.13"),
]


def get(url):
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(2 * (attempt + 1))
        except Exception:
            time.sleep(2 * (attempt + 1))
    return None


def pkg_versions(name):
    d = get(API + urllib.parse.quote(name, safe=""))
    if not d:
        return []
    vs = [(v["versionKey"]["version"], v.get("publishedAt")) for v in d.get("versions", [])]
    return sorted([v for v in vs if v[1]], key=lambda x: x[1])


def version_licences(name, version):
    d = get(API + urllib.parse.quote(name, safe="") + "/versions/" + urllib.parse.quote(version, safe=""))
    return ";".join(d.get("licenses", [])) if d else "NA"


def is_prerelease(v):
    low = v.lower()
    return any(t in low for t in ("-m", "-rc", "snapshot", "alpha", "beta"))


rows, allv = [], {}
for fam, mod, name in AKKA + PEKKO + PLAY:
    vs = pkg_versions(name)
    allv[name] = vs
    if not vs:
        rows.append(dict(family=fam, module=mod, package=name, role="not found", version="", published="", licences=""))
        continue
    picks = [("first release", vs[0])]
    stable = [v for v in vs if not is_prerelease(v[0])]
    # last release before the announcement and first stable release after it
    pre = [v for v in stable if v[1] < "2022-09-07"]
    post = [v for v in stable if v[1] >= "2022-09-07"]
    if pre:
        picks.append(("last stable before 2022-09-07", pre[-1]))
    if post:
        picks.append(("first stable on/after 2022-09-07", post[0]))
    picks.append(("latest", vs[-1]))
    seen = set()
    for role, (ver, pub) in picks:
        if ver in seen:
            continue
        seen.add(ver)
        rows.append(dict(family=fam, module=mod, package=name, role=role, version=ver,
                         published=pub[:10], licences=version_licences(name, ver)))
        time.sleep(0.2)

with open(OUT / "release_calendar.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
with open(OUT / "package_versions.json", "w", encoding="utf-8") as f:
    json.dump({"retrieved": time.strftime("%Y-%m-%d"), "source": API, "packages": allv}, f, indent=1)
for r in rows:
    print(f"{r['family']:5} {r['module']:24} {r['role']:32} {r['version']:12} {r['published']}  {r['licences']}")
