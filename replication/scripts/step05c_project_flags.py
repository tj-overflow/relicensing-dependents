"""Step 5c: registry-based project flags for the whole risk set (no API calls).

Flags:
  vendor       : owner is the Akka/Play vendor or its labs/organizations
  foundation   : Apache (GitHub owner 'apache' or groupId org.apache.*) or Eclipse (owner eclipse*/groupId org.eclipse.*)
  own licence  : SPDX class of the project's own licence at its last pre-event release and its last
                 release by the horizon (permissive / weak_copyleft / strong_copyleft / non_osi / unknown),
                 and whether it changed
  scala3       : project published any _3 artifact before the event; date of first _3 artifact release
  play_user    : any pre-event release declares a Play core artifact (Additional Use Grant relevance)
  provided-only: at the latest pre-event releases, Akka is declared only as 'provided' or only testkit
                 artifacts (integration libraries and platform plug-ins; kept in the risk set, flagged)
  module group : pre-event Akka modules declared (core / http / persistence / cluster / connectors / other)
Outputs: outputs/step05/project_flags.csv
"""
import csv
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "step04"
OUT = ROOT / "outputs" / "step05"
EVENT, HORIZON, PRE_FROM = "2022-09-07", "2025-09-30", "2020-09-07"
VENDOR = {"lightbend", "akka", "playframework", "lightbend-labs", "typesafehub", "akka-js"}
PERM = {"Apache-2.0", "MIT", "BSD-3-Clause", "BSD-2-Clause", "Unlicense", "W3C", "WTFPL", "AFL-2.1", "ISC", "CC0-1.0"}
WEAK = {"LGPL-3.0", "LGPL-2.1", "LGPL-2.1-or-later", "MPL-2.0", "EPL-1.0", "EPL-2.0"}
STRONG = {"GPL-3.0", "GPL-2.0", "GPL-3.0+", "AGPL-3.0"}


def lic_class(s):
    parts = {p for p in s.split(";") if p}
    if not parts:
        return "unknown"
    if "BUSL-1.1" in parts:
        return "non_osi"
    if parts & STRONG:
        return "strong_copyleft"
    if parts & WEAK:
        return "weak_copyleft"
    if parts & PERM:
        return "permissive"
    return "unknown"  # 'non-standard': licence text not mapped to SPDX by deps.dev


def module_group(a):
    a = re.sub(r"_(2\.1[0-3]|3)$", "", a)
    if a.startswith("akka-http") or a.startswith("akka-grpc"):
        return "http"
    if "persistence" in a:
        return "persistence"
    if "cluster" in a or "management" in a or "discovery" in a or a == "akka-remote":
        return "cluster"
    if "alpakka" in a or "kafka" in a or "connectors" in a:
        return "connectors"
    if a in {"akka-actor", "akka-actor-typed", "akka-stream", "akka-stream-typed", "akka-slf4j", "akka-protobuf-v3",
             "akka-serialization-jackson", "akka-pki", "akka-coordination", "akka-protobuf", "akka-osgi"}:
        return "core"
    return "other"


panel = list(csv.DictReader(open(ROOT / "outputs/step04/project_panel.csv", encoding="utf-8")))
risk = list(csv.DictReader(open(ROOT / "outputs/step04/risk_set.csv", encoding="utf-8")))
lic = {}
for name in ("bq_versions.csv", "bq_versions_pekko.csv"):
    for r in csv.DictReader(open(RAW / name, encoding="utf-8")):
        lic[(r["package"], r["version"])] = r["licences"]
deps = defaultdict(list)
for d in csv.DictReader(open(RAW / "release_deps.csv", encoding="utf-8")):
    if d["scope"] != "test" and d["optional"] != "true":
        deps[(d["package"], d["version"])].append(d)

by_proj = defaultdict(list)
for p in panel:
    by_proj[p["project"]].append(p)

rows = []
for r in risk:
    proj = r["project"]
    rs = sorted(by_proj[proj], key=lambda x: x["published"])
    owner = proj.split("/")[1] if proj.startswith("github.com/") else ""
    groups = {x["package"].split(":")[0] for x in rs}
    pre = [x for x in rs if PRE_FROM <= x["published"] < EVENT]
    post = [x for x in rs if EVENT <= x["published"] <= HORIZON]
    l_pre = lic_class(lic.get((pre[-1]["package"], pre[-1]["version"]), "")) if pre else "unknown"
    # most common class among the last release date's artifacts is noisy; use the last release row
    l_post = lic_class(lic.get((post[-1]["package"], post[-1]["version"]), "")) if post else ""
    s3_pre = any(x["package"].endswith("_3") for x in pre)
    s3_first = min((x["published"] for x in rs if x["package"].endswith("_3")), default="")
    mods, play, strong = set(), False, False
    last_pre = {}
    for x in pre:
        last_pre[x["package"]] = x
    for x in last_pre.values():
        for d in deps.get((x["package"], x["version"]), []):
            if d["family"] == "akka" and d["scope"] != "provided" and "testkit" not in d["dep_artifact"]:
                strong = True
    for x in pre:
        for d in deps.get((x["package"], x["version"]), []):
            if d["family"] == "akka":
                mods.add(module_group(d["dep_artifact"]))
            elif d["family"] == "play":
                play = True
    foundation = ("apache" if owner == "apache" or any(g.startswith("org.apache.") for g in groups)
                  else "eclipse" if owner.startswith("eclipse") or any(g.startswith("org.eclipse.") for g in groups)
                  else "")
    rows.append(dict(project=proj, owner=owner or proj, active_post=r["active_post"], outcome=r["outcome_at_horizon"],
                     vendor=int(owner in VENDOR), foundation=foundation, own_licence_pre=l_pre,
                     own_licence_post=l_post, own_licence_changed=int(bool(l_post) and l_post != l_pre),
                     akka_provided_or_testkit_only=int(not strong), scala3_pre_event=int(s3_pre), first_scala3_release=s3_first, play_user_pre=int(play),
                     akka_modules_pre=";".join(sorted(mods))))
with open(OUT / "project_flags.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
act = [x for x in rows if x["active_post"] == "1"]
from collections import Counter
print("active", len(act), "vendor", sum(x["vendor"] for x in act), "foundation", Counter(x["foundation"] for x in act))
print("lic pre", Counter(x["own_licence_pre"] for x in act), "changed", sum(x["own_licence_changed"] for x in act))
print("scala3 pre", sum(x["scala3_pre_event"] for x in act), "play", sum(x["play_user_pre"] for x in act))
print("modules", Counter(m for x in act for m in x["akka_modules_pre"].split(";")))
print([ (x["project"], x["own_licence_pre"], x["own_licence_post"]) for x in act if x["own_licence_changed"]])
