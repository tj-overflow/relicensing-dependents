"""Step 5e: compact coding report from the build-file manifest (registry outcome omitted).

Prints, per project and ref, the build-file lines mentioning akka/pekko/shading, with repeated
lines collapsed, and the first lines of the README. Written to outputs/step05/coding_report.txt.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
man = json.loads((ROOT / "data/raw/step05/build_files/manifest.json").read_text())
out = []
for p in sorted(man, key=lambda x: x["project"]):
    out.append("=" * 100)
    out.append(f"{p['project']}  default={p.get('default_branch')}  {p.get('error', '')}")
    for ref in p.get("refs", []):
        out.append(f"-- {ref['label']} {ref['commit'][:10]} {ref['date']} build_files={ref['n_build_files']}")
        seen = set()
        n = 0
        for f in ref["files"]:
            hits = [h for h in f.get("hits", []) if re.sub(r"^\d+: ", "", h) not in seen]
            for h in hits:
                seen.add(re.sub(r"^\d+: ", "", h))
            if hits and n < 60:
                out.append(f"   {f['path']}")
                for h in hits[:12]:
                    out.append(f"      {h}")
                n += len(hits[:12])
        if n >= 60:
            out.append("   ... truncated")
        if ref.get("readme"):
            key = p["key"]
            lab = re.sub(r"[^\w.@-]", "_", ref["label"])
            rp = ROOT / "data/raw/step05/build_files" / key / lab / ref["readme"][0]["path"]
            if rp.exists():
                txt = [l for l in rp.read_text(encoding="utf-8").splitlines() if l.strip()][:8]
                out.append("   README: " + " | ".join(t.strip()[:120] for t in txt))
(ROOT / "outputs/step05/coding_report.txt").write_text("\n".join(out), encoding="utf-8")
print(len(out), "lines")
