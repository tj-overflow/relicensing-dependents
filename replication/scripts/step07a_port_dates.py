"""Step 7a: Pekko (and Play 3) port availability date for every Akka-family artifact declared by the
risk set before the event.

Mapping rule (by name; documented in the Step 7 note):
  com.typesafe.akka:akka-stream-kafka*            -> org.apache.pekko:pekko-connectors-kafka*
  com.typesafe.akka:akka-X                        -> org.apache.pekko:pekko-X
  com.lightbend.akka:akka-stream-alpakka-X        -> org.apache.pekko:pekko-connectors-X
  com.lightbend.akka:akka-X (jdbc, projection...) -> org.apache.pekko:pekko-X
  com.lightbend.akka.management:akka-X            -> org.apache.pekko:pekko-X
  com.lightbend.akka.discovery:akka-X             -> org.apache.pekko:pekko-X
  com.lightbend.akka.grpc:akka-grpc-X             -> org.apache.pekko:pekko-grpc-X
  com.typesafe.play:play-*                         -> Play 3.0.0 (org.playframework:play)
  special cases: akka-http2-support -> pekko-http-core; akka-discovery-dns -> pekko-discovery (both merged upstream)
Port date = first stable (x.y.z) release of the target on Maven Central (deps.dev API; Scala 2.13,
else 2.12, 3, unsuffixed). No target found -> no port by the horizon.
Outputs: outputs/step07/port_dates.csv (akka_artifact, target, first_stable, version)
"""
import csv
import json
import re
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
O = ROOT / "outputs/step07"
O.mkdir(parents=True, exist_ok=True)
CACHE = ROOT / "data/raw/step07"
CACHE.mkdir(parents=True, exist_ok=True)


def base(g, a):
    a = re.sub(r"_?\$\{[^}]+\}$", "", a)          # property suffixes: _${scala.version}, ${akka.version.suffix}
    a = re.sub(r"_(%%|2\.1\d(\.\d+)?(-[\w.]+)?|3)$", "", a)  # _2.13, _2.13.0-M5, _3, _%%
    return g + ":" + a


def target(b):
    g, a = b.split(":")
    if g == "com.typesafe.play":
        return "org.playframework:play"
    if g == "com.typesafe.akka" and a.startswith("akka-stream-kafka"):
        return "org.apache.pekko:" + a.replace("akka-stream-kafka", "pekko-connectors-kafka")
    if g == "com.lightbend.akka" and a.startswith("akka-stream-alpakka-"):
        return "org.apache.pekko:pekko-connectors-" + a[len("akka-stream-alpakka-"):]
    if a == "akka-http2-support":          # merged into HTTP core (empty artifact since Akka HTTP 10.2)
        return "org.apache.pekko:pekko-http-core"
    if a == "akka-discovery-dns":          # merged into akka-discovery
        return "org.apache.pekko:pekko-discovery"
    if g in ("com.typesafe.akka", "com.lightbend.akka", "com.lightbend.akka.management",
             "com.lightbend.akka.discovery", "com.lightbend.akka.grpc"):
        return "org.apache.pekko:" + a.replace("akka-", "pekko-", 1)
    return None


def versions(name):
    f = CACHE / (name.replace(":", "__") + ".json")
    if f.exists():
        return json.loads(f.read_text())
    url = "https://api.deps.dev/v3/systems/maven/packages/" + urllib.parse.quote(name, safe="")
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "research-script/1.0"}), timeout=60) as r:
            d = json.load(r)
    except urllib.error.HTTPError as e:
        d = {"error": e.code}
    f.write_text(json.dumps(d))
    time.sleep(0.1)
    return d


def first_stable(tgt):
    for suf in ("_2.13", "_2.12", "_3", ""):
        d = versions(tgt + suf)
        vs = [(v.get("publishedAt", "")[:10], v["versionKey"]["version"]) for v in d.get("versions", [])
              if re.fullmatch(r"\d+\.\d+\.\d+", v["versionKey"]["version"]) and v.get("publishedAt")]
        if tgt.startswith("org.playframework"):
            vs = [x for x in vs if x[1].startswith("3.")]
        if vs:
            return min(vs)
    return ("", "")


if __name__ == "__main__":
    v2 = {r["project"]: r for r in csv.DictReader(open(ROOT / "outputs/step05/risk_set_v2.csv", encoding="utf-8"))}
    bases = set()
    for d in csv.DictReader(open(ROOT / "data/raw/step04/release_deps.csv", encoding="utf-8")):
        if d["family"] in ("akka", "play") and d["scope"] != "test" and d["optional"] != "true":
            bases.add(base(d["dep_group"], d["dep_artifact"]))
    rows = []
    for b in sorted(bases):
        t = target(b)
        date, ver = first_stable(t) if t else ("", "")
        rows.append(dict(akka_artifact=b, target=t or "", first_stable=date, version=ver))
    with open(O / "port_dates.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    by = defaultdict(int)
    for r in rows:
        by[r["first_stable"][:7] or "none"] += 1
    print(len(rows), dict(sorted(by.items())))
