"""Step 7b: E1 treatment date per project = month when a Pekko substitute exists for EVERY Akka-family
dependency in its pre-event dependency set (first-party modules and third-party Akka-based upstreams).

First-party : each non-test Akka/Play artifact declared at the latest pre-event release of each artifact
              -> port date from outputs/step07/port_dates.csv (no port -> never).
Third-party : all non-test dependencies of those releases are read from the POMs on Maven Central.
              A dependency D (outside the Akka/Lightbend/Play/Pekko groups and outside the project itself)
              is an Akka-based upstream if D's latest release before the event declared Akka (Step 4 data).
              Port date of D = earliest of (a) the first Pekko-declaring release of D's own project and
              (b) the first release of any artifact named like D with 'akka' replaced by 'pekko' (any group).
              No port by the horizon -> never.
Outputs: outputs/step07/treatment_dates.csv, upstreams.csv
"""
import csv
import re
import time
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
R4, O = ROOT / "data/raw/step04", ROOT / "outputs/step07"
CACHE = ROOT / "data/raw/step07/poms"
CACHE.mkdir(parents=True, exist_ok=True)
OLD_CACHE = ROOT / "data/raw/step05/poms"
EVENT, HORIZON, PRE_FROM = "2022-09-07", "2025-09-30", "2020-09-07"
FIRST = ("com.typesafe.akka", "com.lightbend.akka", "com.typesafe.play", "org.playframework", "org.apache.pekko")
ALIAS = {"github.com/eclipse/ditto": "github.com/eclipse-ditto/ditto",
         "github.com/balmungsan/neotypes": "github.com/neotypes/neotypes"}


def norm_repo(u, pkg):
    if u:
        m = re.search(r"github\.com[:/]+([^/\s]+)/([^/\s#?]+)", u)
        if m:
            r = ("github.com/" + m.group(1) + "/" + re.sub(r"\.git$", "", m.group(2))).lower()
            return ALIAS.get(r, r)
    return "maven:" + pkg.split(":")[0].lower()


def strip(a):
    a = re.sub(r"_?\$\{[^}]+\}$", "", a)
    return re.sub(r"_(%%|2\.1\d(\.\d+)?(-[\w.]+)?|3)$", "", a)


def pom(pkg, ver):
    g, a = pkg.split(":")
    name = f"{g}__{a}__{ver}.pom"
    for c in (CACHE, OLD_CACHE):
        if (c / name).exists():
            return (c / name).read_text(encoding="utf-8", errors="replace")
    url = f"https://repo1.maven.org/maven2/{g.replace('.', '/')}/{a}/{ver}/{a}-{ver}.pom"
    for _ in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "research-script/1.0"}), timeout=30) as r:
                t = r.read().decode("utf-8", "replace")
            (CACHE / name).write_text(t, encoding="utf-8")
            return t
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return ""
        except Exception:
            time.sleep(2)
    return ""


def deps_of(t):
    t = re.sub(r"<dependencyManagement>.*?</dependencyManagement>", "", t, flags=re.S)
    out = []
    for blk in re.findall(r"<dependency>(.*?)</dependency>", t, re.S):
        g = re.search(r"<groupId>\s*([^<]+)", blk)
        a = re.search(r"<artifactId>\s*([^<]+)", blk)
        sc = re.search(r"<scope>\s*([^<]+)", blk)
        op = re.search(r"<optional>\s*([^<]+)", blk)
        if g and a and not (sc and sc.group(1).strip() in ("test",)) and not (op and op.group(1).strip() == "true"):
            out.append(g.group(1).strip() + ":" + a.group(1).strip())
    return out


# ---- Step 4 data: package -> project, release dates, Akka/Pekko status per release ----
repo = {r["package"]: r["repo"] for r in csv.DictReader(open(R4 / "packages.csv", encoding="utf-8"))}
fam = defaultdict(set)
for d in csv.DictReader(open(R4 / "release_deps.csv", encoding="utf-8")):
    if d["scope"] != "test" and d["optional"] != "true":
        fam[(d["package"], d["version"])].add(d["family"])
rels = defaultdict(list)
for r in csv.DictReader(open(R4 / "releases.csv", encoding="utf-8")):
    if r["published"]:
        rels[r["package"]].append((r["published"], r["version"]))
proj_of = {p: norm_repo(repo.get(p, ""), p) for p in rels}
by_base = defaultdict(list)  # (groupId, artifact without Scala suffix) -> packages
for p in rels:
    by_base[(p.split(":")[0], strip(p.split(":")[1]))].append(p)
# first Pekko-declaring release per project; earliest release per 'pekko-named' base artifact
first_pekko_proj, first_pekko_name = {}, {}
for p, vs in rels.items():
    for d, v in vs:
        if "pekko" in fam.get((p, v), set()):
            pr = proj_of[p]
            first_pekko_proj[pr] = min(first_pekko_proj.get(pr, d), d)
        a = strip(p.split(":")[1])
        if "pekko" in a:
            first_pekko_name[a] = min(first_pekko_name.get(a, d), d)
# Step 5 corrected switch dates (shading / wrapper overrides) for risk-set projects
for r in csv.DictReader(open(ROOT / "outputs/step05/risk_set_v2.csv", encoding="utf-8")):
    if r["first_switch_v2"]:
        first_pekko_proj[r["project"]] = min(first_pekko_proj.get(r["project"], r["first_switch_v2"]), r["first_switch_v2"])
# ports that live inside Apache Pekko itself (e.g. ch.megard:akka-http-cors -> org.apache.pekko:pekko-http-cors)
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from step07a_port_dates import first_stable  # noqa: E402


def asf_port(a):
    d, _ = first_stable("org.apache.pekko:" + a.replace("akka", "pekko"))
    return d


akka_based_pre = {}
for p, vs in rels.items():
    pre = [x for x in vs if x[0] < EVENT]
    if pre:
        d, v = max(pre)
        akka_based_pre[p] = "akka" in fam.get((p, v), set())

ports = {r["akka_artifact"]: r["first_stable"] for r in csv.DictReader(open(O / "port_dates.csv", encoding="utf-8"))}
v2 = {r["project"]: r for r in csv.DictReader(open(ROOT / "outputs/step05/risk_set_v2.csv", encoding="utf-8"))
      if r["vendor"] == "0"}
last_pre = {}
for p in csv.DictReader(open(ROOT / "outputs/step04/project_panel.csv", encoding="utf-8")):
    if p["project"] in v2 and PRE_FROM <= p["published"] < EVENT:
        k = (p["project"], p["package"])
        if k not in last_pre or p["published"] >= last_pre[k][0]:
            last_pre[k] = (p["published"], p["version"])

first_party = defaultdict(dict)
for d in csv.DictReader(open(R4 / "release_deps.csv", encoding="utf-8")):
    k = (d["package"], d["version"])
    if d["family"] in ("akka", "play") and d["scope"] != "test" and d["optional"] != "true":
        b = d["dep_group"] + ":" + strip(d["dep_artifact"])
        first_party[k][b] = ports.get(b, "")

up_rows, t_rows = [], []
n_pom = 0
for proj in sorted(v2):
    keys = [(pkg, ver) for (pr, pkg), (_, ver) in last_pre.items() if pr == proj]
    fp = {}
    for k in keys:
        fp.update(first_party.get(k, {}))
    ups = {}
    for pkg, ver in keys:
        t = pom(pkg, ver)
        n_pom += 1
        for dname in deps_of(t):
            g = dname.split(":")[0]
            if g.startswith(FIRST) or "${" in dname:
                continue
            cands = by_base.get((g, strip(dname.split(":")[1])), [])
            if not cands or not any(akka_based_pre.get(c) for c in cands):
                continue
            uprojs = Counter(proj_of[c] for c in cands)  # Scala variants can carry different (stale) repo links
            if proj in uprojs:
                continue
            uproj = uprojs.most_common(1)[0][0]
            a = strip(dname.split(":")[1])
            dates = [x for x in [first_pekko_proj.get(u, "") for u in uprojs] + [first_pekko_name.get(a.replace("akka", "pekko"), "")]
                     if x and x >= "2022-09-07"]
            if not dates and "akka" in a:
                d_asf = asf_port(a)
                if d_asf:
                    dates = [d_asf]
            ups[g + ":" + a] = (uproj, min(dates) if dates else "")
    for u, (up, d) in ups.items():
        up_rows.append(dict(project=proj, upstream=u, upstream_project=up, port_date=d))
    fp_dates = list(fp.values())
    t_first = "" if (not fp_dates or "" in fp_dates) else max(fp_dates)
    up_dates = [d for _, d in ups.values()]
    t_third = "" if "" in up_dates else (max(up_dates) if up_dates else "n/a")
    if t_first == "" or t_third == "":
        t_all = ""
    else:
        t_all = max(x for x in (t_first, t_third) if x != "n/a")
    r = v2[proj]
    t_rows.append(dict(project=proj, owner=r["owner"], active_post=r["active_post"], outcome_v2=r["outcome_v2"],
                       first_switch_v2=r["first_switch_v2"], n_first_party=len(fp),
                       unported_first_party=";".join(b for b, d in fp.items() if not d),
                       T_first_party=t_first, n_upstreams=len(ups), T_third_party=t_third, T_all=t_all,
                       scala3_pre_event=r["scala3_pre_event"], akka_modules_pre=r["akka_modules_pre"],
                       akka_provided_or_testkit_only=r["akka_provided_or_testkit_only"]))
for name, rows in (("treatment_dates.csv", t_rows), ("upstreams.csv", up_rows)):
    with open(O / name, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
print("projects", len(t_rows), "poms read", n_pom, "upstream links", len(up_rows))
