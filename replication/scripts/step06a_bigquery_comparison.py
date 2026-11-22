"""Step 6a: dependents of the comparison libraries (cats-effect, fs2, http4s, ZIO) from deps.dev BigQuery.

Same snapshot partition as Step 4. Slim columns (no properties / dependencyManagement), as in step04f:
sbt-published POMs carry literal versions. The comparison rule is fixed in outputs/step06/comparison_rule.md.
Extracted dependency families: the four comparison libraries plus Akka/Pekko (to detect overlap).
Outputs: data/raw/step06/bq_cmp_declared.jsonl, bq_cmp_versions.csv, bq_run_log.json
Usage: python -I scripts/step06a_bigquery_comparison.py --project <ID> [--run] [--max-gb 40]
"""
import argparse
import csv
import json
from pathlib import Path

from google.cloud import bigquery

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "step06"
OUT.mkdir(parents=True, exist_ok=True)
DS = "bigquery-public-data.deps_dev_v1"
SNAP = "2026-11-02 21:00:03.179237+00:00"  # same partition as Step 4
CMP = """(STARTS_WITH(x.Name, 'org.typelevel:cats-effect') OR STARTS_WITH(x.Name, 'co.fs2:fs2-')
          OR STARTS_WITH(x.Name, 'org.http4s:http4s-') OR STARTS_WITH(x.Name, 'dev.zio:zio_')
          OR STARTS_WITH(x.Name, 'dev.zio:zio-streams_'))"""
FAM = CMP[:-1] + """ OR STARTS_WITH(x.Name, 'com.typesafe.akka:') OR STARTS_WITH(x.Name, 'com.lightbend.akka')
          OR STARTS_WITH(x.Name, 'org.apache.pekko:'))"""
OWN = """(STARTS_WITH(r.Name, 'org.typelevel:') OR STARTS_WITH(r.Name, 'co.fs2:')
          OR STARTS_WITH(r.Name, 'org.http4s:') OR STARTS_WITH(r.Name, 'dev.zio:'))"""
CANDS = f"""SELECT DISTINCT r.Name FROM `{DS}.MavenRequirements` r
    WHERE r.SnapshotAt = TIMESTAMP('{SNAP}') AND NOT {OWN}
      AND EXISTS(SELECT 1 FROM UNNEST(r.Dependencies) x WHERE {CMP})"""
QS = {
    "bq_cmp_declared": f"""WITH cands AS ({CANDS})
        SELECT r.Name AS package, r.Version AS version,
               ARRAY(SELECT AS STRUCT x.Name, x.Version, x.Scope, x.Optional
                     FROM UNNEST(r.Dependencies) x WHERE {FAM}) AS deps
        FROM `{DS}.MavenRequirements` r JOIN cands c ON r.Name = c.Name
        WHERE r.SnapshotAt = TIMESTAMP('{SNAP}')""",
    "bq_cmp_versions": f"""WITH cands AS ({CANDS})
        SELECT v.Name AS package, v.Version AS version, v.UpstreamPublishedAt AS published,
               ARRAY_TO_STRING(v.Licenses, ';') AS licences,
               (SELECT l.URL FROM UNNEST(v.Links) l WHERE l.Label = 'SOURCE_REPO' LIMIT 1) AS source_repo,
               v.VersionInfo.IsRelease AS is_release
        FROM `{DS}.PackageVersions` v JOIN cands c ON v.Name = c.Name
        WHERE v.SnapshotAt = TIMESTAMP('{SNAP}') AND v.System = 'MAVEN'""",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--max-gb", type=float, default=40)
    a = ap.parse_args()
    c = bigquery.Client(project=a.project)
    log = {"snapshot": SNAP}
    for name, q in QS.items():
        gb = c.query(q, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)).total_bytes_processed / 1e9
        print(f"{name}: estimated {gb:.2f} GB", flush=True)
        log[name] = {"estimated_gb": round(gb, 3)}
        if not a.run or gb > a.max_gb:
            continue
        job = c.query(q)
        rows = list(job.result())
        log[name].update(billed_gb=round(job.total_bytes_billed / 1e9, 3), rows=len(rows), job_id=job.job_id)
        if name == "bq_cmp_versions":
            with open(OUT / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["package", "version", "published", "licences", "source_repo", "is_release"])
                for r in rows:
                    w.writerow([r["package"], r["version"], r["published"].isoformat() if r["published"] else "",
                                r["licences"], r["source_repo"] or "", r["is_release"]])
        else:
            with open(OUT / f"{name}.jsonl", "w", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps({"package": r["package"], "version": r["version"],
                                        "deps": [dict(d) for d in r["deps"]]}) + "\n")
        print(f"  wrote {len(rows)} rows; billed {log[name]['billed_gb']} GB", flush=True)
    (OUT / "bq_run_log.json").write_text(json.dumps(log, indent=1))


if __name__ == "__main__":
    main()
