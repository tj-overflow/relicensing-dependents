"""Step 5f: compact per-reference coding summary (registry outcome omitted).

For each project and reference commit, from the saved build files:
  akka / pekko artifacts mentioned, version definitions, lines suggesting test/provided scope,
  shading or relocation lines, and the build files that mention akka or pekko.
Output: outputs/step05/coding_report_compact.txt
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BF = ROOT / "data/raw/step05/build_files"
man = json.loads((BF / "manifest.json").read_text())
ART = re.compile(r"[\"'>](akka-[\w.-]+?|pekko-[\w.-]+?)(?:_\$\{[^}]+\}|_2\.1\d|_3)?[\"'<]")
VER = re.compile(r"(akka|pekko|alpakka)[\w.-]*[Vv]ersion\w*\s*(=|:=|>|:)\s*\S+|(akka|pekko)[\w.-]*\.version>[^<]+<")
SCOPE = re.compile(r"(akka|pekko).*(%\s*Test|%\s*\"test\"|Provided|\"provided\"|Optional|% IntegrationTest)", re.I)
SHADE = re.compile(r"(relocat|shade|shaded).*(akka|pekko)|(akka|pekko).*(relocat|shade)", re.I)
RELEASE = re.compile(r"^(v?\d|release|series|branch-|stable|akka|pekko|.*\.x$|.*-x$|\d)", re.I)
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
        arts, vers, scope, shade, files = set(), [], [], [], []
        for f in ref["files"]:
            fp = BF / p["key"] / lab / f["path"]
            if not fp.exists():
                continue
            txt = fp.read_text(encoding="utf-8", errors="replace")
            if re.search(r"akka|pekko", txt, re.I):
                files.append(f["path"])
            for line in txt.splitlines():
                l = line.strip()
                if l.startswith(("//", "#", "<!--", "*")):
                    continue
                for m in ART.finditer(line):
                    arts.add(m.group(1))
                if VER.search(line) and l[:160] not in vers:
                    vers.append(l[:160])
                if SCOPE.search(line) and l[:140] not in scope:
                    scope.append(l[:140])
                if SHADE.search(line) and l[:140] not in shade:
                    shade.append(l[:140])
        ak = sorted(a for a in arts if a.startswith("akka"))
        pe = sorted(a for a in arts if a.startswith("pekko"))
        sig = (tuple(sorted(arts)), tuple(vers), tuple(shade))
        if sig == prev:
            out.append(f"-- {ref['label']} {ref['date']}: same as previous reference")
            continue
        prev = sig
        out.append(f"-- {ref['label']} {ref['date']} files={ref['n_build_files']} akka/pekko-files={len(files)}")
        out.append(f"   AKKA({len(ak)}): {', '.join(ak[:14])}{' ...' if len(ak) > 14 else ''}")
        out.append(f"   PEKKO({len(pe)}): {', '.join(pe[:14])}{' ...' if len(pe) > 14 else ''}")
        for v in vers[:8]:
            out.append(f"   VER {v}")
        for s in scope[:5]:
            out.append(f"   SCOPE {s}")
        for s in shade[:4]:
            out.append(f"   SHADE {s}")
        out.append(f"   FILES {', '.join(files[:8])}{' ...' if len(files) > 8 else ''}")
        if ref.get("readme"):
            rp = BF / p["key"] / lab / ref["readme"][0]["path"]
            if rp.exists():
                t = [x.strip()[:110] for x in rp.read_text(encoding="utf-8", errors="replace").splitlines()
                     if x.strip() and not x.strip().startswith(("[!", "![", "<", "[!["))][:3]
                out.append("   README " + " | ".join(t))
(ROOT / "outputs/step05/coding_report_compact.txt").write_text("\n".join(out), encoding="utf-8")
print(len(out))
