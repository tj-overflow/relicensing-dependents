"""Step 3b: Scala-version availability of each Akka and Pekko module, with licences.

For each module and Scala binary version (2.12, 2.13, 3), records the first stable
release, its licence, and the latest release on Maven Central (via deps.dev).
Output: outputs/step03/scala_availability.csv
Usage: python -I scripts/step03b_scala3_and_crossbuilds.py
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

MODULES = {
    "akka": [
        ("actor", "com.typesafe.akka:akka-actor"),
        ("stream", "com.typesafe.akka:akka-stream"),
        ("cluster-typed", "com.typesafe.akka:akka-cluster-typed"),
        ("persistence-typed", "com.typesafe.akka:akka-persistence-typed"),
        ("http", "com.typesafe.akka:akka-http"),
        ("grpc-runtime", "com.lightbend.akka.grpc:akka-grpc-runtime"),
        ("management", "com.lightbend.akka.management:akka-management"),
        ("kafka", "com.typesafe.akka:akka-stream-kafka"),
        ("alpakka-s3", "com.lightbend.akka:akka-stream-alpakka-s3"),
        ("persistence-jdbc", "com.lightbend.akka:akka-persistence-jdbc"),
        ("persistence-cassandra", "com.typesafe.akka:akka-persistence-cassandra"),
        ("projection-core", "com.lightbend.akka:akka-projection-core"),
    ],
    "pekko": [
        ("actor", "org.apache.pekko:pekko-actor"),
        ("stream", "org.apache.pekko:pekko-stream"),
        ("cluster-typed", "org.apache.pekko:pekko-cluster-typed"),
        ("persistence-typed", "org.apache.pekko:pekko-persistence-typed"),
        ("http", "org.apache.pekko:pekko-http"),
        ("grpc-runtime", "org.apache.pekko:pekko-grpc-runtime"),
        ("management", "org.apache.pekko:pekko-management"),
        ("kafka", "org.apache.pekko:pekko-connectors-kafka"),
        ("alpakka-s3", "org.apache.pekko:pekko-connectors-s3"),
        ("persistence-jdbc", "org.apache.pekko:pekko-persistence-jdbc"),
        ("persistence-cassandra", "org.apache.pekko:pekko-persistence-cassandra"),
        ("projection-core", "org.apache.pekko:pekko-projection-core"),
    ],
}


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


def stable(v):
    low = v.lower()
    return not any(t in low for t in ("-m", "-rc", "snapshot", "alpha", "beta"))


rows = []
for fam, mods in MODULES.items():
    for mod, base in mods:
        for sv in ("2.12", "2.13", "3"):
            name = f"{base}_{sv}"
            d = get(API + urllib.parse.quote(name, safe=""))
            vs = sorted([(v.get("publishedAt", "")[:10], v["versionKey"]["version"])
                         for v in (d or {}).get("versions", []) if v.get("publishedAt")])
            st = [x for x in vs if stable(x[1])]
            if not st:
                rows.append(dict(family=fam, module=mod, scala=sv, first_stable="", first_date="",
                                 first_licence="", latest="", latest_date="", n_versions=len(vs)))
                continue
            first = st[0]
            lic = get(API + urllib.parse.quote(name, safe="") + "/versions/" + urllib.parse.quote(first[1], safe=""))
            rows.append(dict(family=fam, module=mod, scala=sv, first_stable=first[1], first_date=first[0],
                             first_licence=";".join((lic or {}).get("licenses", [])),
                             latest=vs[-1][1], latest_date=vs[-1][0], n_versions=len(vs)))
            time.sleep(0.2)

with open(OUT / "scala_availability.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
for r in rows:
    print(f"{r['family']:5} {r['module']:22} {r['scala']:4} first={r['first_stable']:10} {r['first_date']} {r['first_licence']:11} latest={r['latest']} {r['latest_date']}")
