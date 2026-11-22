"""Step 7-pooled scoping: Elasticsearch risk set, outcomes, substitute timing and a within-vendor control.

Event 2021-01-14 (announcement); last Apache 7.10.2; restricted from 7.11.0 (2021-02-10, ELv2/SSPL);
AGPL option from 8.16.0 (2024-11-12). Restricted families: org.elasticsearch:* (server, x-pack, plugins
as libraries), org.elasticsearch.client:elasticsearch-rest-high-level-client, transport, x-pack-transport,
org.elasticsearch.plugin:*. Open vendor path: org.elasticsearch.client:elasticsearch-rest-client(-sniffer),
co.elastic.clients:* (from 2021-09-30). Fork: org.opensearch* (Maven 1.0.0 on 2021-08-27).
Definitions mirror the Akka risk set: unit = repository; risk set = latest pre-event release (2019-01-14 to
2021-01-13) of some artifact declares a restricted artifact (non-test, non-optional); outcome at the
horizon from artifacts maintained within 6 months of the project's last release.
Within-vendor control: projects whose pre-event releases declare ONLY the open low-level client.
Outputs: outputs/step07_pooled/elastic_counts.json, elastic_risk_set.csv
"""
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
R, O = ROOT / "data/raw/step07_pooled", ROOT / "outputs/step07_pooled"
EVENT, PRE_FROM, HORIZON, AGPL = "2021-01-14", "2019-01-14", "2024-11-11", "2024-11-12"
OPEN_LOW = {"elasticsearch-rest-client", "elasticsearch-rest-client-sniffer"}


def vt(v):
    return tuple(int(x) for x in re.findall(r"\d+", v.split("-")[0])[:3]) if v else ()


def norm_repo(u, pkg):
    if u:
        m = re.search(r"github\.com[:/]+([^/\s]+)/([^/\s#?]+)", u)
        if m:
            return ("github.com/" + m.group(1) + "/" + re.sub(r"\.git$", "", m.group(2))).lower()
    return "maven:" + pkg.split(":")[0].lower()


def kind(name, ver):
    g, a = name.split(":", 1)
    if g.startswith("org.opensearch"):
        return "opensearch"
    if g == "co.elastic.clients":
        return "vendor_open"
    if g == "org.elasticsearch.client" and a in OPEN_LOW:
        return "vendor_open"
    if g.startswith("org.elasticsearch"):
        t = vt(ver)
        if not t:
            return "es_unresolved"
        if t <= (7, 10, 2):
            return "es_open"
        return "es_agpl" if t >= (8, 16, 0) else "es_restricted"
    return None


vers, latest_repo = {}, {}
for r in csv.DictReader(open(R / "bq_es_versions.csv", encoding="utf-8")):
    vers[(r["package"], r["version"])] = (r["published"] or "")[:10]
    if r["source_repo"] and (r["published"] or "") >= latest_repo.get(r["package"], ("", ""))[0]:
        latest_repo[r["package"]] = (r["published"] or "", r["source_repo"])
rel_kinds = {}
for l in open(R / "bq_es_declared.jsonl", encoding="utf-8"):
    j = json.loads(l)
    ks = set()
    for x in j["deps"]:
        v = x.get("Version") or ""
        if (x.get("Scope") or "").lower() == "test" or str(x.get("Optional")).lower() == "true":
            continue
        if "${" in v:
            v = ""  # property-set version (not resolved in the slim extraction): presence only
        k = kind(x["Name"], v)
        if k:
            ks.add(k)
    rel_kinds[(j["package"], j["version"])] = ks
by_proj = defaultdict(list)
for (pkg, ver), pub in vers.items():
    if pub:
        by_proj[norm_repo(latest_repo.get(pkg, ("", ""))[1], pkg)].append((pub, pkg, ver, rel_kinds.get((pkg, ver), set())))


def status(ks):
    es = ks & {"es_open", "es_restricted", "es_agpl", "es_unresolved"}
    if "opensearch" in ks and (es or "vendor_open" in ks):
        return "dual"
    if "opensearch" in ks:
        return "switch"
    if "es_restricted" in ks:
        return "upgrade"
    if "es_agpl" in ks:
        return "upgrade_agpl"
    if "es_open" in ks or "es_unresolved" in ks:
        return "freeze"
    if "vendor_open" in ks:
        return "vendor_open"
    return "removed"


rows, control = [], []
for proj, rs in by_proj.items():
    rs.sort()
    pre = [x for x in rs if PRE_FROM <= x[0] < EVENT]
    last_pre = {}
    for x in pre:
        last_pre[x[1]] = x
    lp = set().union(*[x[3] for x in last_pre.values()]) if last_pre else set()
    treated = bool(lp & {"es_open", "es_unresolved"})
    ctrl = bool(lp) and lp <= {"vendor_open"}
    if not (treated or ctrl):
        continue
    post = [x for x in rs if EVENT <= x[0] <= HORIZON]
    last_post = {}
    for x in post:
        last_post[x[1]] = x
    if last_post:
        pl = max(x[0] for x in last_post.values())
        y, m = int(pl[:4]), int(pl[5:7])
        cut = f"{y - (1 if m <= 6 else 0):04d}-{(m - 7) % 12 + 1:02d}{pl[7:10]}"
        last_post = {k: x for k, x in last_post.items() if x[0] >= cut}
    fin = set().union(*[x[3] for x in last_post.values()]) if last_post else set()
    out = "no_release" if not post else status(fin)
    first_os = min((x[0] for x in post if "opensearch" in x[3]), default="")
    first_vo = min((x[0] for x in post if "vendor_open" in x[3] and not (x[3] & {"es_open", "es_restricted"})), default="")
    row = dict(project=proj, group="treated" if treated else "control_lowlevel_only", active=int(bool(post)),
               outcome=out, first_opensearch=first_os, first_vendor_open_only=first_vo,
               ever_restricted=int(any("es_restricted" in x[3] for x in post)),
               ever_opensearch=int(bool(first_os)))
    (rows if treated else control).append(row)

with open(O / "elastic_risk_set.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows + control)
act = [r for r in rows if r["active"]]
res = dict(event=EVENT, horizon=HORIZON,
           note="versions set by properties/dependencyManagement are unresolved in this slim extraction: "
                "they count for presence (risk set, OpenSearch, vendor-open) but freeze vs upgrade is unknown",
           outcome_freeze_includes_unresolved=sum(1 for r in act if r["outcome"] == "freeze"),
           treated_risk_set=len(rows), treated_active=len(act),
           treated_owners_active=len({r["project"].split("/")[1] if r["project"].startswith("github") else r["project"] for r in act}),
           outcome_active=dict(Counter(r["outcome"] for r in act)),
           ever_opensearch_active=sum(r["ever_opensearch"] for r in act),
           ever_restricted_active=sum(r["ever_restricted"] for r in act),
           first_opensearch_by_half_year=dict(sorted(Counter(
               r["first_opensearch"][:4] + ("H1" if r["first_opensearch"][5:7] <= "06" else "H2")
               for r in act if r["first_opensearch"]).items())),
           control_lowlevel_only=len(control), control_active=sum(r["active"] for r in control))
(O / "elastic_counts.json").write_text(json.dumps(res, indent=1))
print(json.dumps(res, indent=1))
