"""Step 12e: hold-up spillover. Declarations of Lightbend's other libraries by Akka and comparison dependents.

Hold-up (the model's h * dpi term) is a fear about the supplier, not about one licence. If it moved Akka dependents,
they should also drop or avoid Lightbend libraries whose licence did not change in September 2022. The legal channel
predicts no change for those libraries. Extracted families (all releases of the Step 4 Akka panel packages and the
Step 6 comparison packages, same snapshot partition as Steps 4 and 6):
  com.typesafe:*                 config, ssl-config (Apache 2.0, unchanged; Pekko also depends on them)
  com.typesafe.scala-logging:*   scala-logging (Apache 2.0, lightbend-labs)
  com.typesafe.slick:*           Slick (BSD-2)
  com.typesafe.play:*, org.playframework:*   Play (Apache 2.0; built on Akka, so confounded, reported apart)
  com.lightbend.*                Lightbend's other groups (classified in step12f; Akka-branded ones went BSL)
A hard cap on billed bytes (--max-gb) guards the run: the dry run of a clustered IN-list filter under-reports bytes,
and a full partition read is 9.5 GB.
Outputs: data/raw/step12/bq_lightbend_declared.jsonl, bq_spillover_log.json
Usage: python scripts/step12e_bigquery_spillover.py --project <ID> [--run] [--max-gb 12]
"""
import argparse
import csv
import json
from pathlib import Path

from google.cloud import bigquery

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "step12"
OUT.mkdir(parents=True, exist_ok=True)
DS = "bigquery-public-data.deps_dev_v1"
SNAP = "2026-11-02 21:00:03.179237+00:00"
LB = """(STARTS_WITH(x.Name, 'com.typesafe:') OR STARTS_WITH(x.Name, 'com.typesafe.scala-logging:')
         OR STARTS_WITH(x.Name, 'com.typesafe.slick:') OR STARTS_WITH(x.Name, 'com.typesafe.play:')
         OR STARTS_WITH(x.Name, 'org.playframework:') OR STARTS_WITH(x.Name, 'com.lightbend'))"""
Q = f"""SELECT r.Name AS package, r.Version AS version,
           ARRAY(SELECT AS STRUCT x.Name, x.Version, x.Scope, x.Optional
                 FROM UNNEST(r.Dependencies) x WHERE {LB}) AS deps
    FROM `{DS}.MavenRequirements` r
    WHERE r.SnapshotAt = TIMESTAMP('{SNAP}') AND r.Name IN UNNEST(@names)"""


def names():
    s = {r["package"] for r in csv.DictReader(open(ROOT / "outputs/step04/project_panel.csv", encoding="utf-8"))}
    s |= {r["package"] for r in csv.DictReader(open(ROOT / "data/raw/step06/bq_cmp_versions.csv", encoding="utf-8"))}
    return sorted(s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--max-gb", type=float, default=12)
    a = ap.parse_args()
    ns = names()
    c = bigquery.Client(project=a.project)
    params = [bigquery.ArrayQueryParameter("names", "STRING", ns)]
    dry = c.query(Q, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False, query_parameters=params))
    gb = dry.total_bytes_processed / 1e9
    log = {"snapshot": SNAP, "n_packages": len(ns), "dry_run_gb": round(gb, 3), "cap_gb": a.max_gb}
    print(f"{len(ns)} packages; dry run {gb:.3f} GB (under-reports for clustered IN filters); cap {a.max_gb} GB", flush=True)
    if a.run:
        cfg = bigquery.QueryJobConfig(query_parameters=params, maximum_bytes_billed=int(a.max_gb * 1e9))
        job = c.query(Q, job_config=cfg)
        rows = list(job.result())
        log.update(billed_gb=round(job.total_bytes_billed / 1e9, 3), processed_gb=round(job.total_bytes_processed / 1e9, 3),
                   rows=len(rows), job_id=job.job_id)
        with open(OUT / "bq_lightbend_declared.jsonl", "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps({"package": r["package"], "version": r["version"],
                                    "deps": [dict(d) for d in r["deps"]]}) + "\n")
        print(f"wrote {len(rows)} rows; billed {log['billed_gb']} GB", flush=True)
    (OUT / "bq_spillover_log.json").write_text(json.dumps(log, indent=1))


if __name__ == "__main__":
    main()
