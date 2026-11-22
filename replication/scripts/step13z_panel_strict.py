"""Step 13z: the strict-codebook panel.

Runs step11a_panels.py unchanged except that provided-scope dependencies are treated as not declared, for the
Elasticsearch dependents and for their comparison dependents alike (both filters in build_es). The Akka panel is
rebuilt as in Step 11 and is not used. Output goes to outputs/step13/strict/ (Step 11 files are not touched).
Outputs: outputs/step13/strict/panel.csv, projects.csv, panel_summary.json
"""
from pathlib import Path

S = Path(__file__).resolve().parent / "step11a_panels.py"
src = S.read_text(encoding="utf-8")
old_filter = '        if d["scope"] == "test" or d["optional"] == "true":\n'
new_filter = '        if d["scope"] in ("test", "provided") or d["optional"] == "true":\n'
assert src.count(old_filter) == 2, "expected the two build_es scope filters"
src = src.replace(old_filter, new_filter)
old_out = 'O = ROOT / "outputs/step11"'
assert src.count(old_out) == 1
src = src.replace(old_out, 'O = ROOT / "outputs/step13/strict"')
exec(compile(src, str(S), "exec"), {"__file__": str(S), "__name__": "__main__"})
