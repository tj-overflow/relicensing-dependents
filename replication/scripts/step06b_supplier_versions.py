"""Step 6b: publication dates of supplier versions (documented deps.dev API, GetPackage).

Lines: Akka core (akka-actor), Akka HTTP (akka-http), cats-effect, fs2 (fs2-core), http4s (http4s-core),
ZIO (zio). Each version's date is the earliest across its Scala 2.12 / 2.13 / 3 artifacts.
Output: data/raw/step06/supplier_versions.csv (line, version, published, licences)
"""
import csv
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINES = {"akka": "com.typesafe.akka:akka-actor", "akka_http": "com.typesafe.akka:akka-http",
         "cats_effect": "org.typelevel:cats-effect", "fs2": "co.fs2:fs2-core", "http4s": "org.http4s:http4s-core",
         "zio": "dev.zio:zio"}
best = {}
for line, base in LINES.items():
    for sv in ("2.12", "2.13", "3"):
        name = f"{base}_{sv}"
        url = "https://api.deps.dev/v3/systems/maven/packages/" + urllib.parse.quote(name, safe="")
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "research-script/1.0"}), timeout=60) as r:
                d = json.load(r)
        except Exception as e:
            print(name, "error", e)
            continue
        for v in d.get("versions", []):
            ver, pub = v["versionKey"]["version"], (v.get("publishedAt") or "")[:10]
            if not pub:
                continue
            k = (line, ver)
            if k not in best or pub < best[k]:
                best[k] = pub
        print(name, len(d.get("versions", [])))
with open(ROOT / "data/raw/step06/supplier_versions.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["line", "version", "published"])
    for (line, ver), pub in sorted(best.items(), key=lambda x: (x[0][0], x[1])):
        w.writerow([line, ver, pub])
