"""Step 5h: detect switching through third-party Pekko wrappers (registry blind spot found in Step 5).

The Step 4 extraction kept only dependencies in the Akka/Pekko/Play groups, so a project that moves
to e.g. com.github.pjfanning:pekko-http-circe (which brings Pekko transitively) looks like 'none'.
For every active project coded freeze / upgrade / removed, fetch from Maven Central the POM of the
latest release (by 2025-09-30) of each artifact released after the event, and record non-test
dependencies whose groupId or artifactId contains 'pekko' (and, for completeness, 'akka').
Output: outputs/step05/wrapper_check.csv
"""
import csv
import re
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data/raw/step05/poms"
CACHE.mkdir(parents=True, exist_ok=True)
EVENT, HORIZON = "2022-09-07", "2025-09-30"
risk = {r["project"]: r for r in csv.DictReader(open(ROOT / "outputs/step04/risk_set.csv", encoding="utf-8"))
        if r["active_post"] == "1" and r["outcome_at_horizon"] in ("freeze", "upgrade", "removed")}
latest = {}
for p in csv.DictReader(open(ROOT / "outputs/step04/project_panel.csv", encoding="utf-8")):
    if p["project"] in risk and EVENT <= p["published"] <= HORIZON:
        k = (p["project"], p["package"])
        if k not in latest or p["published"] >= latest[k]["published"]:
            latest[k] = p
        # also every post-Pekko-1.0 release the registry codes 'none' (no Akka/Pekko-group dependency):
        # a parallel Pekko line built on wrappers looks like this (e.g. kanadi 0.20.0)
        if p["published"] >= "2023-07-10" and p["status"] == "none":
            latest[(p["project"], p["package"] + "@" + p["version"])] = p


def pom(pkg, ver):
    g, a = pkg.split(":")
    f = CACHE / f"{g}__{a}__{ver}.pom"
    if f.exists():
        return f.read_text(encoding="utf-8", errors="replace")
    url = f"https://repo1.maven.org/maven2/{g.replace('.', '/')}/{a}/{ver}/{a}-{ver}.pom"
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "research-script/1.0"}), timeout=30) as r:
                t = r.read().decode("utf-8", "replace")
            f.write_text(t, encoding="utf-8")
            return t
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return ""
        except Exception:
            time.sleep(2)
    return ""


out = []
for (proj, key), p in sorted(latest.items()):
    pkg = p["package"]
    t = pom(pkg, p["version"])
    hits = []
    managed = "pekko" in "".join(re.findall(r"<dependencyManagement>.*?</dependencyManagement>", t, re.S)).lower()
    t_dep = re.sub(r"<dependencyManagement>.*?</dependencyManagement>", "", t, flags=re.S)  # managed versions are not dependencies
    for blk in re.findall(r"<dependency>(.*?)</dependency>", t_dep, re.S):
        g = re.search(r"<groupId>\s*([^<]+)", blk)
        a = re.search(r"<artifactId>\s*([^<]+)", blk)
        sc = re.search(r"<scope>\s*([^<]+)", blk)
        if not (g and a) or (sc and sc.group(1).strip() == "test"):
            continue
        name = f"{g.group(1).strip()}:{a.group(1).strip()}"
        if re.search(r"pekko|akka", name, re.I) and not name.startswith(("com.typesafe.akka:", "com.lightbend.akka")):
            hits.append(name)
    out.append(dict(project=proj, registry=risk[proj]["outcome_at_horizon"], package=pkg, version=p["version"],
                    published=p["published"], pom_found=int(bool(t)), pekko_managed_only=int(managed),
                    pekko_wrappers=";".join(h for h in hits if "pekko" in h.lower()),
                    akka_wrappers=";".join(h for h in hits if "pekko" not in h.lower())))
    time.sleep(0.05)
with open(ROOT / "outputs/step05/wrapper_check.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(out[0]))
    w.writeheader()
    w.writerows(out)
proj_hit = defaultdict(set)
for r in out:
    if r["pekko_wrappers"]:
        proj_hit[(r["project"], r["registry"])].update(r["pekko_wrappers"].split(";"))
print("artifacts checked", len(out), "poms found", sum(r["pom_found"] for r in out), "projects", len(risk))
for k, v in sorted(proj_hit.items()):
    print(k, sorted(v)[:4])
print("Pekko only in dependencyManagement (BOMs):", sorted({r["project"] for r in out if r["pekko_managed_only"]}))
