"""Step 8c: Elasticsearch risk set and outcome coding (mirrors the Akka Step 4 definitions).

Restricted artifacts are identified from licence data, not assumed: for every org.elasticsearch* artifact
declared (non-test) by the extraction, the licence of its 7.17.0 version (else its first version >= 7.11)
is read from the deps.dev API. Restricted = Elastic-2.0/SSPL; open = Apache (e.g. low-level REST client,
ES-Hadoop). co.elastic.clients:* is the vendor's Apache client (from 2021-09-30).
Version rule within restricted artifacts: <= 7.10.2 open (freeze), 7.11.0-8.15.x restricted (upgrade),
>= 8.16.0 AGPL option (upgrade_agpl).
Release kinds -> outcome at the horizon (2024-11-11, the day before 8.16.0), from artifacts maintained
within 6 months of the project's last release:
  dual (OpenSearch and Elasticsearch), switch (OpenSearch only), upgrade, upgrade_agpl, freeze,
  vendor_open (only Apache vendor artifacts), spring_only (only via Spring Data), removed.
Flags: vendor (owner elastic), fork-affiliated (opensearch-project; opendistro-for-elasticsearch, AWS's
pre-fork distribution, added in Step 9), spring-projects; Spring Data use.
Outputs: outputs/step08/es_artifact_licences.csv, es_risk_set.csv, es_project_panel.csv, es_counts.json
"""
import csv
import json
import re
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
R8, O = ROOT / "data/raw/step08", ROOT / "outputs/step08"
O.mkdir(parents=True, exist_ok=True)
API = R8 / "api"
API.mkdir(exist_ok=True)
EVENT, PRE_FROM, HORIZON, H2 = "2021-01-14", "2019-01-14", "2024-11-11", "2025-09-30"
OS_FIRST, VENDOR_CLIENT_FIRST = "2021-08-27", "2021-09-30"


def vt(v):
    return tuple(int(x) for x in re.findall(r"\d+", v.split("-")[0])[:3]) if v else ()


def api(name, ver=None):
    key = name.replace(":", "__") + (f"__{ver}" if ver else "")
    f = API / (key + ".json")
    if f.exists():
        return json.loads(f.read_text())
    url = "https://api.deps.dev/v3/systems/maven/packages/" + urllib.parse.quote(name, safe="")
    if ver:
        url += "/versions/" + urllib.parse.quote(ver, safe="")
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "research-script/1.0"}), timeout=60) as r:
            d = json.load(r)
    except urllib.error.HTTPError as e:
        d = {"error": e.code}
    f.write_text(json.dumps(d))
    time.sleep(0.05)
    return d


def norm_repo(u, pkg):
    if u:
        m = re.search(r"github\.com[:/]+([^/\s]+)/([^/\s#?]+)", u)
        if m:
            return ("github.com/" + m.group(1) + "/" + re.sub(r"\.git$", "", m.group(2))).lower()
    return "maven:" + pkg.split(":")[0].lower()


deps = [r for r in csv.DictReader(open(R8 / "es_release_deps.csv", encoding="utf-8"))
        if r["scope"] != "test" and r["optional"] != "true"]
# Step 9: releases whose deps.dev record has an empty family list but whose POM on Maven Central declares
# family dependencies (step09h_empty_record_check.py) are supplemented from the POM.
CHECK = ROOT / "data/raw/step09/empty_record_check.csv"
n_supplemented = 0
if CHECK.exists():
    for r in csv.DictReader(open(CHECK, encoding="utf-8")):
        for d in json.loads(r["family"]):
            if d["scope"] != "test" and d["optional"] != "true":
                deps.append(dict(package=r["package"], version=r["version"], dep=d["dep"], dep_version=d["dep_version"],
                                 scope=d["scope"], optional=d["optional"], resolution="pom_check"))
                n_supplemented += 1
# ---- licence class of each declared org.elasticsearch* artifact ----
names = sorted({r["dep"] for r in deps if r["dep"].startswith("org.elasticsearch")})
lic_class = {}
with open(O / "es_artifact_licences.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["artifact", "probe_version", "licences", "class"])
    for nm in names:
        d = api(nm)
        vs = [v["versionKey"]["version"] for v in d.get("versions", [])]
        probe = "7.17.0" if "7.17.0" in vs else next((v for v in vs if (7, 11) <= vt(v)[:2] and re.fullmatch(r"\d+\.\d+\.\d+", v)), None)
        if probe is None:
            lic_class[nm] = "no_post_event_version"
            w.writerow([nm, "", "", lic_class[nm]])
            continue
        lic = api(nm, probe).get("licenses", [])
        c = "restricted" if any(x in ("Elastic-2.0", "SSPL-1.0") or "Elastic" in x for x in lic) else (
            "open" if lic else "unknown")
        lic_class[nm] = c
        w.writerow([nm, probe, ";".join(lic), c])


def kind(dep, v):
    if "testcontainers" in dep:
        return None  # dev-services/test helpers (e.g. org.opensearch:opensearch-testcontainers), added in Step 9
    if dep.startswith("org.opensearch"):
        return "opensearch"
    if dep.startswith("co.elastic.clients"):
        return "vendor_new_client"
    if dep.startswith("org.springframework"):
        return "spring_data"
    c = lic_class.get(dep, "unknown")
    if dep.startswith("org.elasticsearch:elasticsearch-spark-"):
        c = "open"  # ES-Hadoop/Spark connectors stayed Apache (artifact name may carry an unresolved ${scala...})
    if c == "open":
        return "vendor_open"
    if c == "no_post_event_version":
        return None  # never relicensed: Apache utilities (jna, securesm, securemock), third-party forks
                     # under the group (didi, analysis-ik), artifacts discontinued before 2021
    if c in ("restricted", "unknown"):
        t = vt(v)
        if not t:
            return "es_unresolved"
        if t <= (7, 10, 2):
            return "es_open"
        return "es_agpl" if t >= (8, 16, 0) else "es_restricted"
    return None


rel = defaultdict(set)
for r in deps:
    k = kind(r["dep"], r["dep_version"])
    if k:
        rel[(r["package"], r["version"])].add(k)
latest_repo, pubs = {}, {}
for r in csv.DictReader(open(ROOT / "data/raw/step07_pooled/bq_es_versions.csv", encoding="utf-8")):
    d = (r["published"] or "")[:10]
    pubs[(r["package"], r["version"])] = d
    if r["source_repo"] and d >= latest_repo.get(r["package"], ("", ""))[0]:
        latest_repo[r["package"]] = (d, r["source_repo"])
by_proj = defaultdict(list)
for (pkg, ver), d in pubs.items():
    if d and PRE_FROM <= d <= H2:
        by_proj[norm_repo(latest_repo.get(pkg, ("", ""))[1], pkg)].append((d, pkg, ver, rel.get((pkg, ver), set())))
ES_ANY = {"es_open", "es_restricted", "es_agpl", "es_unresolved"}


def status(ks):
    ks = set(ks)
    if "vendor_new_client" in ks:
        ks.add("vendor_open")
    if "opensearch" in ks and (ks & ES_ANY or "vendor_open" in ks):
        return "dual"
    if "opensearch" in ks:
        return "switch"
    if "es_restricted" in ks:
        return "upgrade"
    if "es_agpl" in ks:
        return "upgrade_agpl"
    if "es_open" in ks:
        return "freeze"
    if "es_unresolved" in ks:
        return "es_version_unresolved"
    if "vendor_open" in ks:
        return "vendor_open"
    if "spring_data" in ks:
        return "spring_only"
    return "removed"


def outcome_at(rs, horizon):
    post = [x for x in rs if EVENT <= x[0] <= horizon]
    if not post:
        return "no_release", post
    last = {}
    for x in post:
        last[x[1]] = x
    pl = max(x[0] for x in last.values())
    y, m = int(pl[:4]), int(pl[5:7])
    cut = f"{y - (1 if m <= 6 else 0):04d}-{(m - 7) % 12 + 1:02d}{pl[7:10]}"
    fin = set().union(*[x[3] for x in last.values() if x[0] >= cut])
    return status(fin), post


rows, panel = [], []
for proj, rs in by_proj.items():
    rs.sort()
    pre = [x for x in rs if x[0] < EVENT]
    last_pre = {}
    for x in pre:
        last_pre[x[1]] = x
    lp = set().union(*[x[3] for x in last_pre.values()]) if last_pre else set()
    direct = bool(lp & {"es_open", "es_unresolved", "es_restricted"})
    spring = (not direct) and "spring_data" in lp
    lowlevel_only = (not direct) and bool(lp) and lp <= {"vendor_open", "vendor_new_client"}
    if not (direct or spring or lowlevel_only):
        continue
    group = "direct" if direct else ("spring_only" if spring else "control_open_vendor_only")
    out, post = outcome_at(rs, HORIZON)
    out2, _ = outcome_at(rs, H2)
    owner = proj.split("/")[1] if proj.startswith("github.com/") else proj
    rows.append(dict(project=proj, owner=owner, group=group, n_artifacts=len(last_pre), n_pre_releases=len(pre),
                     active_post=int(bool(post)), active_post_os=int(any(x[0] >= OS_FIRST for x in post)),
                     outcome_2024_11=out, outcome_2025_09=out2,
                     first_opensearch=min((x[0] for x in post if "opensearch" in x[3]), default=""),
                     first_restricted=min((x[0] for x in post if "es_restricted" in x[3]), default=""),
                     first_vendor_client=min((x[0] for x in post if "vendor_new_client" in x[3]), default=""),
                     pre_unresolved=int("es_unresolved" in lp and not lp & {"es_open"}),
                     spring_user_pre=int("spring_data" in lp),
                     vendor=int(owner == "elastic"), fork_affiliated=int(owner in ("opensearch-project", "opendistro-for-elasticsearch")),
                     spring_projects=int(owner == "spring-projects")))
    for x in rs:
        panel.append(dict(project=proj, published=x[0], package=x[1], version=x[2], status=status(x[3]),
                          kinds=";".join(sorted(x[3]))))
for name, rr in (("es_risk_set.csv", rows), ("es_project_panel.csv", panel)):
    with open(O / name, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rr[0]))
        w.writeheader()
        w.writerows(rr)

d = [r for r in rows if r["group"] == "direct"]
da = [r for r in d if r["active_post"] and not r["vendor"] and not r["fork_affiliated"]]
res = dict(event=EVENT, horizon_main=HORIZON, horizon_post_reversal=H2, pom_check_rows_added=n_supplemented,
           artifact_licence_classes=dict(Counter(lic_class.values())),
           direct_risk_set=len(d), direct_active_nonvendor=len(da),
           direct_active_owners=len({r["owner"] for r in da}),
           direct_active_after_opensearch=sum(r["active_post_os"] for r in da),
           pre_version_unresolved=sum(r["pre_unresolved"] for r in da),
           outcome_2024_11=dict(Counter(r["outcome_2024_11"] for r in da)),
           outcome_2025_09=dict(Counter(r["outcome_2025_09"] for r in da)),
           ever_opensearch=sum(1 for r in da if r["first_opensearch"]),
           ever_restricted=sum(1 for r in da if r["first_restricted"]),
           ever_vendor_new_client=sum(1 for r in da if r["first_vendor_client"]),
           first_opensearch_by_half=dict(sorted(Counter(
               r["first_opensearch"][:4] + ("H1" if r["first_opensearch"][5:7] <= "06" else "H2")
               for r in da if r["first_opensearch"]).items())),
           spring_user_pre_among_direct=sum(r["spring_user_pre"] for r in da),
           spring_only_group=dict(n=sum(1 for r in rows if r["group"] == "spring_only"),
                                  active=sum(1 for r in rows if r["group"] == "spring_only" and r["active_post"])),
           control_open_vendor_only=dict(n=sum(1 for r in rows if r["group"] == "control_open_vendor_only"),
                                         active=sum(1 for r in rows if r["group"] == "control_open_vendor_only" and r["active_post"])),
           vendor_projects=[r["project"] for r in d if r["vendor"]],
           fork_affiliated=[r["project"] for r in d if r["fork_affiliated"]])
(O / "es_counts.json").write_text(json.dumps(res, indent=1))
print(json.dumps(res, indent=1))
