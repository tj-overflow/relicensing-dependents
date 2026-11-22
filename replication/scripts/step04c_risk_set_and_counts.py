"""Step 4c: build the fixed risk set and compute the Step 4 kill-test counts.

Inputs : data/raw/step04/packages.csv, releases.csv, release_deps.csv (from step04b)
Licence of each declared Akka (artifact, version) is looked up in deps.dev (cached);
versions absent from Maven Central are flagged "not_on_central" (Akka 2.9+ are BSL).
Outputs: outputs/step04/akka_dep_licences.csv, project_panel.csv, risk_set.csv, counts.json
Usage: python -I scripts/step04c_risk_set_and_counts.py
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
RAW = ROOT / "data" / "raw" / "step04"
OUT = ROOT / "outputs" / "step04"
OUT.mkdir(parents=True, exist_ok=True)
EVENT, PEKKO1, HORIZON = "2022-09-07", "2023-07-10", "2025-09-30"
PRE_FROM = "2020-09-07"
UA = {"User-Agent": "research-script/1.0"}


def rd(name):
    return list(csv.DictReader(open(RAW / name, encoding="utf-8")))


def http_json(url):
    for a in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(2 * (a + 1))
        except Exception:
            time.sleep(2 * (a + 1))
    return None


# Repositories that moved; POMs of older releases carry the old URL (found in Step 5)
ALIAS = {"github.com/eclipse/ditto": "github.com/eclipse-ditto/ditto",
         "github.com/balmungsan/neotypes": "github.com/neotypes/neotypes"}


def norm_repo(u, fallback):
    if u:
        m = re.search(r"github\.com[:/]+([^/\s]+)/([^/\s#?]+)", u)
        if m:
            r = ("github.com/" + m.group(1) + "/" + re.sub(r"\.git$", "", m.group(2))).lower()
            return ALIAS.get(r, r)
    # no GitHub link: group by Maven groupId (one groupId is usually one project, e.g. OpenDaylight)
    g, a = fallback.split(":", 1)
    return f"maven:{g}".lower()


pk = {r["package"]: r for r in rd("packages.csv")}
rels = rd("releases.csv")
deps = rd("release_deps.csv")

# licence of each declared Akka dependency version
lic_path = OUT / "akka_dep_licences.csv"
lic = {}
bq_lic = RAW / "bq_akka_licences.csv"  # licences of all Akka-group versions on Maven Central (BigQuery)
if bq_lic.exists():
    lic = {(r["artifact"], r["version"]): r["licence"] for r in csv.DictReader(open(bq_lic, encoding="utf-8"))}
need = {(d["dep_group"] + ":" + d["dep_artifact"], d["dep_version"]) for d in deps
        if d["family"] == "akka" and d["dep_version"] and "${" not in d["dep_version"]}
for art, ver in sorted(need - set(lic)):
    if bq_lic.exists():  # absent from the full Maven Central listing
        lic[(art, ver)] = "not_on_central"
        continue
    v = http_json("https://api.deps.dev/v3/systems/maven/packages/" + urllib.parse.quote(art, safe="")
                  + "/versions/" + urllib.parse.quote(ver, safe=""))
    lic[(art, ver)] = ";".join(v.get("licenses", [])) if v else "not_on_central"
    time.sleep(0.1)
with open(lic_path, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["artifact", "version", "licence"])
    for (a, v), l in sorted(lic.items()):
        w.writerow([a, v, l])

# release-level classification (non-test, non-optional scopes)
rel_dep = defaultdict(list)
for d in deps:
    if d["scope"] in ("test",) or d["optional"] == "true":
        continue
    rel_dep[(d["package"], d["version"])].append(d)


def classify(key):
    ds = rel_dep.get(key, [])
    ak = [d for d in ds if d["family"] == "akka"]
    pe = [d for d in ds if d["family"] == "pekko"]
    akl = set()
    unresolved = 0
    for d in ak:
        l = lic.get((d["dep_group"] + ":" + d["dep_artifact"], d["dep_version"]))
        if l is None:
            unresolved += 1
        elif "BUSL" in l or l == "not_on_central":
            akl.add("bsl")
        else:
            akl.add("open")
    hidden = sum(1 for d in ak if lic.get((d["dep_group"] + ":" + d["dep_artifact"], d["dep_version"])) == "not_on_central")
    if ak and pe:
        s = "mixed"
    elif pe:
        s = "pekko"
    elif ak:
        s = "akka_bsl" if "bsl" in akl else ("akka_open" if akl else "akka_unresolved")
    else:
        s = "none"
    return s, hidden, unresolved


proj_rel = defaultdict(list)
for r in rels:
    if r["pom"] == "missing" or not r["published"]:
        continue
    p = pk.get(r["package"], {})
    proj = norm_repo(p.get("repo") or r["scm"], r["package"])
    s, hidden, unres = classify((r["package"], r["version"]))
    proj_rel[proj].append(dict(package=r["package"], version=r["version"], published=r["published"],
                               status=s, hidden_akka=hidden, unresolved=unres))

panel_rows, risk_rows = [], []
for proj, rs in proj_rel.items():
    rs.sort(key=lambda x: x["published"])
    pre = [x for x in rs if PRE_FROM <= x["published"] < EVENT]
    if not pre:
        continue
    # latest pre-event release of each artifact
    last_pre = {}
    for x in pre:
        last_pre[x["package"]] = x
    base_akka = any(x["status"].startswith("akka") for x in last_pre.values())
    if not base_akka:
        continue
    post = [x for x in rs if EVENT <= x["published"] <= HORIZON]
    post_p1 = [x for x in post if x["published"] >= PEKKO1]
    ever = {x["status"] for x in post}
    switched = any(x["status"] in ("pekko", "mixed") for x in post)
    # dual: same project has both an akka-dependent and a pekko-dependent release within 6 months
    ak_dates = [x["published"] for x in post if x["status"].startswith("akka")]
    pe_dates = [x["published"] for x in post if x["status"] in ("pekko", "mixed")]
    dual = any(abs((int(a[:4]) * 12 + int(a[5:7])) - (int(b[:4]) * 12 + int(b[5:7]))) <= 6
               for a in ak_dates for b in pe_dates)
    upgraded = any(x["status"] == "akka_bsl" for x in post)
    hidden = sum(x["hidden_akka"] for x in post)
    # status at horizon: latest post release per artifact
    last_post = {}
    for x in post:
        last_post[x["package"]] = x
    # only artifacts still maintained: last release within 6 months of the project's last release
    if last_post:
        proj_last = max(x["published"] for x in last_post.values())
        cutoff = f"{int(proj_last[:4]) - (1 if int(proj_last[5:7]) <= 6 else 0):04d}-{(int(proj_last[5:7]) - 7) % 12 + 1:02d}{proj_last[7:10]}"
        last_post = {k: x for k, x in last_post.items() if x["published"] >= cutoff}
    final = {x["status"] for x in last_post.values()}
    if not post:
        outcome = "no_release"
    elif final & {"pekko", "mixed"} and final & {"akka_open", "akka_bsl", "akka_unresolved"}:
        outcome = "dual_or_partial"
    elif final & {"pekko", "mixed"}:
        outcome = "switch"
    elif "akka_bsl" in final:
        outcome = "upgrade"
    elif "akka_open" in final or "akka_unresolved" in final:
        outcome = "freeze"
    else:
        outcome = "removed"
    risk_rows.append(dict(project=proj, n_artifacts=len(last_pre), n_pre_releases=len(pre), n_post_releases=len(post),
                          n_post_pekko1_releases=len(post_p1), active_post=int(bool(post)),
                          active_post_pekko1=int(bool(post_p1)), ever_switched=int(switched), dual_6m=int(dual),
                          ever_upgraded_bsl=int(upgraded), hidden_akka_decls=hidden, outcome_at_horizon=outcome,
                          first_switch=min(pe_dates) if pe_dates else "",
                          first_bsl=min([x["published"] for x in post if x["status"] == "akka_bsl"], default="")))
    for x in rs:
        panel_rows.append(dict(project=proj, **x))

for name, rows in (("risk_set.csv", risk_rows), ("project_panel.csv", panel_rows)):
    with open(OUT / name, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

n = len(risk_rows)
act = [r for r in risk_rows if r["active_post"]]
act1 = [r for r in risk_rows if r["active_post_pekko1"]]
from collections import Counter
counts = dict(
    risk_set_projects=n,
    active_post_event=len(act),
    active_post_pekko1=len(act1),
    ever_switched=sum(r["ever_switched"] for r in risk_rows),
    ever_switched_among_active=sum(r["ever_switched"] for r in act),
    non_switchers_among_active=sum(1 - r["ever_switched"] for r in act),
    ever_upgraded_bsl=sum(r["ever_upgraded_bsl"] for r in risk_rows),
    dual_within_6m=sum(r["dual_6m"] for r in risk_rows),
    projects_with_hidden_akka_decls=sum(1 for r in risk_rows if r["hidden_akka_decls"]),
    outcome_at_horizon=Counter(r["outcome_at_horizon"] for r in risk_rows),
    outcome_at_horizon_active=Counter(r["outcome_at_horizon"] for r in act),
    github_linked=sum(1 for r in risk_rows if r["project"].startswith("github.com/")),
)
(OUT / "counts.json").write_text(json.dumps(counts, indent=1, default=dict))
print(json.dumps(counts, indent=1, default=dict))
