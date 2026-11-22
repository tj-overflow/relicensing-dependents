"""Re-run the offline analysis pipeline (Steps 11-15) from the included data.

Collection scripts (BigQuery, deps.dev API, GitHub API, Maven Central) are not run here; see README.md.
Also not run: the Step 12 text steps and the Step 14 coding page (they need issue text, which is not shipped).
Step 16a runs offline from the saved tag listings (data/raw/step16/tags.json).
Usage (from this folder):  python run_all.py [--from SCRIPT] [--rscript PATH]
"""
import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PIPELINE = [
    "step11a_panels.py", "step11b_estimates.py", "step11c_inference.py", "step11d_heterogeneity.py",
    "step11e_descriptives.py", "step11f_figures.py",
    "step12a_mechanisms.py", "step12d_conversion.py", "step12f_spillover.py",
    "step13z_panel_strict.py", "step13a_robustness.py", "step13b_honest.py", "step13c_foundation_ri.py",
    "step13d_export_es.py", "step13e_honestdid.R",
    "step13f_lu_feasibility.py", "step13g_lu_build.py", "step13h_lu_estimate.py",
    "step14a_figure_launch.py", "step14d_validation_score.py",
    "step15a_freeze_count.py", "step15b_launch_estimates.py",
    "step15e_r4_lists.py exposure-packages", "step15e_r4_lists.py candidates", "step15e_r4_lists.py extract",
    "step15f_benchmark_build.py", "step15g_r4_estimates.py", "step15h_figure_outcomes.py",
    "step16a_tag_check.py --offline",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default=None)
    ap.add_argument("--rscript", default=os.environ.get("RSCRIPT") or shutil.which("Rscript") or "Rscript")
    a = ap.parse_args()
    todo = PIPELINE[next(i for i, s in enumerate(PIPELINE) if s.startswith(a.start)):] if a.start else PIPELINE
    for s in todo:
        script, *args = s.split()
        path = str(HERE / "scripts" / script)
        cmd = [a.rscript, path] if script.endswith(".R") else [sys.executable, path, *args]
        t = time.time()
        print(f"== {s}", flush=True)
        r = subprocess.run(cmd, cwd=HERE)
        if r.returncode:
            sys.exit(f"{s} failed with exit code {r.returncode}")
        print(f"   done in {time.time() - t:.0f}s", flush=True)


if __name__ == "__main__":
    main()
