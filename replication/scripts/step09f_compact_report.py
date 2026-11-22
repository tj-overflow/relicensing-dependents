"""Step 9f: compact per-reference coding summary for the Elasticsearch validation sample (registry outcome
omitted). Adapts step05f: Elasticsearch/OpenSearch artifacts, version definitions, parents/BOMs, scope and
shading lines, release-like branches only, consecutive identical references collapsed.
Output: outputs/step09/coding_report_compact.txt
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BF = ROOT / "data/raw/step09/build_files"
man = json.loads((BF / "manifest.json").read_text())
ART = re.compile(r"(org\.elasticsearch[\w.]*|co\.elastic\.clients|org\.opensearch[\w.]*)\s*[:<\"'/]+\s*"
                 r"(?:</groupId>\s*<artifactId>)?([\w.${}-]+)", re.I)
ART_POM = re.compile(r"<groupId>\s*(org\.elasticsearch[\w.]*|co\.elastic\.clients|org\.opensearch[\w.]*)\s*</groupId>", re.I)
AID = re.compile(r"<artifactId>\s*([\w.${}-]+)\s*</artifactId>")
VER = re.compile(r"(elastic|opensearch|\bes)[\w.-]*[._-]?version\w*\s*(=|:=|>|:)\s*\S+|"
                 r"<(elasticsearch|opensearch|es|elastic)[\w.-]*\.?version>[^<]+<|"
                 r"(elasticsearch|opensearch)[\w-]*\s*=\s*\"[\d.]+\"", re.I)
PARENT = re.compile(r"<parent>|spring-boot-(starter-)?parent|spring-boot-dependencies|org\.springframework\.boot['\"]? version|"
                    r"io\.spring\.dependency-management|platform\(|<scope>import</scope>", re.I)
SCOPE = re.compile(r"(<scope>(test|provided)</scope>|<optional>true</optional>|testImplementation|compileOnly|% ?Test)", re.I)
SHADE = re.compile(r"(relocat|shade).*(elastic|opensearch)|(elastic|opensearch).*(relocat|shade)", re.I)
RELEASE = re.compile(r"^(v?\d|release|series|branch-|stable|es|elastic|opensearch|.*\.x$|.*-x$|\d)", re.I)
out = []
for p in sorted(man, key=lambda x: x["project"]):
    out.append("=" * 90)
    out.append(f"{p['project']} {'ERROR ' + p['error'][:80] if 'error' in p else ''}")
    prev = None
    for ref in p.get("refs", []):
        name = ref["label"].split("@")[1]
        if ref["label"].startswith("branch") and not RELEASE.search(name):
            continue
        lab = re.sub(r"[^\w.@-]", "_", ref["label"])
        arts, vers, pars, scope, shade, files = set(), [], [], [], [], []
        for f in ref["files"]:
            fp = BF / p["key"] / lab / f["path"]
            if not fp.exists():
                continue
            txt = fp.read_text(encoding="utf-8", errors="replace")
            if not re.search(r"elastic|opensearch", txt, re.I):
                if fp.name == "pom.xml" and f["path"].count("/") == 0:
                    for l in txt.splitlines():
                        if PARENT.search(l) or (pars and pars[-1].startswith("<parent>") and AID.search(l)):
                            pars.append(l.strip()[:140])
                continue
            files.append(f["path"])
            lines = txt.splitlines()
            for i, line in enumerate(lines):
                l = line.strip()
                if l.startswith(("//", "#", "<!--", "*")):
                    continue
                m = ART_POM.search(line)
                if m:
                    nxt = " ".join(x.strip() for x in lines[i:i + 6])
                    a = AID.search(nxt)
                    sc = SCOPE.search(" ".join(x.strip() for x in lines[i:i + 8]).split("</dependency>")[0])
                    arts.add(f"{m.group(1)}:{a.group(1) if a else '?'}" + (f" [{sc.group(1)}]" if sc else "")
                             + f" ({f['path']})")
                else:
                    for m in ART.finditer(line):
                        sc = SCOPE.search(line)
                        arts.add(f"{m.group(1)}:{m.group(2)}" + (f" [{sc.group(1)}]" if sc else "") + f" ({f['path']})")
                if VER.search(line) and l[:160] not in vers:
                    vers.append(l[:160])
                if f["path"].count("/") == 0 and (PARENT.search(line) or (i and "<parent>" in lines[i - 1])) and l[:140] not in pars:
                    pars.append(l[:140])
                if SHADE.search(line) and l[:140] not in shade:
                    shade.append(l[:140])
        sig = (tuple(sorted(arts)), tuple(vers), tuple(shade))
        if sig == prev:
            out.append(f"-- {ref['label']} {ref['date']}: same as previous reference")
            continue
        prev = sig
        out.append(f"-- {ref['label']} {ref['date']} files={ref['n_build_files']} es/os-files={len(files)}")
        al = sorted(arts)
        for a in al[:18]:
            out.append(f"   ART {a}")
        if len(al) > 18:
            out.append(f"   ART ... {len(al) - 18} more")
        for v in vers[:8]:
            out.append(f"   VER {v}")
        for s in pars[:6]:
            out.append(f"   PARENT {s}")
        for s in shade[:4]:
            out.append(f"   SHADE {s}")
        if ref.get("readme"):
            rp = BF / p["key"] / lab / ref["readme"][0]["path"]
            if rp.exists():
                t = [x.strip()[:110] for x in rp.read_text(encoding="utf-8", errors="replace").splitlines()
                     if x.strip() and not x.strip().startswith(("[!", "![", "<", "[!["))][:2]
                out.append("   README " + " | ".join(t))
(ROOT / "outputs/step09/coding_report_compact.txt").write_text("\n".join(out), encoding="utf-8")
print(len(out), "lines")
