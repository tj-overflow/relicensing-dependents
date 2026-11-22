"""Step 8a: declared Elasticsearch/OpenSearch dependencies (with properties, dependencyManagement, parents) from deps.dev BigQuery. Same method as step04d.
Run only bq_declared (65.6 GB); versions come from step07p (bq_es_versions.csv) and parent POMs are
resolved from Maven Central in step08b (free), instead of the 26 GB versions and 62 GB parents queries.

Dataset: bigquery-public-data.deps_dev_v1 (official bulk channel of deps.dev).
All queries read a single snapshot partition (literal SnapshotAt) and only the needed
(sub)columns, which keeps scans to a few GB (the *Latest views scan 1-2 TB; avoid them).

Modes:
  schema  - list tables/columns (metadata only)
  dryrun  - estimate bytes scanned (no cost)
  run     - run queries whose estimate is below --max-gb
Usage:
  python -I scripts/step04d_bigquery_dependents.py --project <ID> dryrun
  python -I scripts/step04d_bigquery_dependents.py --project <ID> run --max-gb 50
Outputs (data/raw/step04/): bq_schema.json, bq_declared.jsonl, bq_versions.csv, bq_parents.jsonl,
                            bq_run_log.json
"""
import argparse
import json
from pathlib import Path

from google.cloud import bigquery

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "step08"
OUT.mkdir(parents=True, exist_ok=True)
DS = "bigquery-public-data.deps_dev_v1"

FAM = """(STARTS_WITH(x.Name, 'org.elasticsearch') OR STARTS_WITH(x.Name, 'co.elastic.clients:')
          OR STARTS_WITH(x.Name, 'org.opensearch') OR STARTS_WITH(x.Name, 'org.springframework.data:spring-data-elasticsearch')
          OR STARTS_WITH(x.Name, 'org.springframework.boot:spring-boot-starter-data-elasticsearch'))"""
AKKA = """(STARTS_WITH(x.Name, 'org.elasticsearch') OR STARTS_WITH(x.Name, 'co.elastic.clients:') OR STARTS_WITH(x.Name, 'org.opensearch'))"""
OWN = """(STARTS_WITH(r.Name, 'org.elasticsearch') OR STARTS_WITH(r.Name, 'co.elastic.clients:')
          OR STARTS_WITH(r.Name, 'org.opensearch'))"""
PROPS = r"REGEXP_CONTAINS(LOWER(p.Name), r'elastic|opensearch|^es[._-]|lucene|spring')"

CANDS = f"""
  SELECT DISTINCT r.Name FROM `{DS}.MavenRequirements` r
  WHERE r.SnapshotAt = TIMESTAMP('{{snap}}') AND NOT {OWN}
    AND (EXISTS(SELECT 1 FROM UNNEST(r.Dependencies) x WHERE {AKKA})
         OR EXISTS(SELECT 1 FROM UNNEST(r.DependencyManagement) x WHERE {AKKA}))"""

QUERIES = {
    # every version of every candidate package (packages that ever declared Akka), with its
    # declared Akka/Pekko/Play requirements, dependencyManagement entries and relevant properties
    "bq_declared": f"""
        WITH cands AS ({CANDS})
        SELECT r.Name AS package, r.Version AS version,
               r.Parent.Name AS parent_name, r.Parent.Version AS parent_version,
               ARRAY(SELECT AS STRUCT x.Name, x.Version, x.Scope, x.Type, x.Optional
                     FROM UNNEST(r.Dependencies) x WHERE {FAM}) AS deps,
               ARRAY(SELECT AS STRUCT x.Name, x.Version, x.Scope, x.Type
                     FROM UNNEST(r.DependencyManagement) x WHERE {FAM}) AS dm,
               ARRAY(SELECT AS STRUCT p.Name, p.Value FROM UNNEST(r.Properties) p WHERE {PROPS}) AS props
        FROM `{DS}.MavenRequirements` r JOIN cands c ON r.Name = c.Name
        WHERE r.SnapshotAt = TIMESTAMP('{{snap}}')
    """,
    # publication date, licences, source repo for every version of the candidate packages
    "bq_versions": f"""
        WITH cands AS ({CANDS})
        SELECT v.Name AS package, v.Version AS version, v.UpstreamPublishedAt AS published,
               ARRAY_TO_STRING(v.Licenses, ';') AS licences,
               (SELECT l.URL FROM UNNEST(v.Links) l WHERE l.Label = 'SOURCE_REPO' LIMIT 1) AS source_repo,
               v.VersionInfo.IsRelease AS is_release
        FROM `{DS}.PackageVersions` v JOIN cands c ON v.Name = c.Name
        WHERE v.SnapshotAt = TIMESTAMP('{{snap}}') AND v.System = 'MAVEN'
    """,
    # parent POMs referenced by candidate versions (for property / dependencyManagement resolution)
    "bq_parents": f"""
        WITH cands AS ({CANDS}),
        par AS (SELECT DISTINCT r.Parent.Name AS n, r.Parent.Version AS v
                FROM `{DS}.MavenRequirements` r JOIN cands c ON r.Name = c.Name
                WHERE r.SnapshotAt = TIMESTAMP('{{snap}}') AND r.Parent.Name IS NOT NULL)
        SELECT r.Name AS package, r.Version AS version,
               r.Parent.Name AS parent_name, r.Parent.Version AS parent_version,
               ARRAY(SELECT AS STRUCT x.Name, x.Version, x.Scope, x.Type
                     FROM UNNEST(r.DependencyManagement) x WHERE {FAM}) AS dm,
               ARRAY(SELECT AS STRUCT p.Name, p.Value FROM UNNEST(r.Properties) p WHERE {PROPS}) AS props
        FROM `{DS}.MavenRequirements` r JOIN par ON r.Name = par.n AND r.Version = par.v
        WHERE r.SnapshotAt = TIMESTAMP('{{snap}}')
    """,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("mode", choices=["schema", "dryrun", "run"])
    ap.add_argument("--max-gb", type=float, default=50.0)
    ap.add_argument("--only", default="", help="comma-separated query names to run (e.g. bq_declared)")
    a = ap.parse_args()
    client = bigquery.Client(project=a.project)

    if a.mode == "schema":
        q = f"SELECT table_name, column_name, data_type FROM `{DS}.INFORMATION_SCHEMA.COLUMNS` ORDER BY table_name, ordinal_position"
        rows = [dict(r) for r in client.query(q).result()]
        (OUT / "bq_schema.json").write_text(json.dumps(rows, indent=1))
        print(len(rows), "columns")
        return

    snap = list(client.query(f"SELECT MAX(Time) AS t FROM `{DS}.Snapshots`").result())[0]["t"]
    print("snapshot:", snap)
    log = {"snapshot": snap.isoformat(), "queries": {}}
    for name, sql in QUERIES.items():
        if a.only and name not in a.only.split(","):
            continue
        sql = sql.replace("{snap}", snap.isoformat())
        dry = client.query(sql, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False))
        gb = dry.total_bytes_processed / 1e9
        print(f"{name}: estimated {gb:,.2f} GB")
        log["queries"][name] = {"estimated_gb": round(gb, 3)}
        if a.mode != "run":
            continue
        if gb > a.max_gb:
            print(f"  skipped (above {a.max_gb} GB)")
            continue
        job = client.query(sql)
        rows = list(job.result())
        log["queries"][name].update(billed_gb=round((job.total_bytes_billed or 0) / 1e9, 3), rows=len(rows),
                                    job_id=job.job_id)
        if name == "bq_versions":
            import csv
            with open(OUT / "bq_versions.csv", "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["package", "version", "published", "licences", "source_repo", "is_release"])
                for r in rows:
                    w.writerow([r["package"], r["version"], r["published"].isoformat() if r["published"] else "",
                                r["licences"], r["source_repo"] or "", r["is_release"]])
        else:
            with open(OUT / f"{name}.jsonl", "w", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps({k: (list(map(dict, v)) if isinstance(v, list) else v) for k, v in r.items()}) + "\n")
        print(f"  wrote {len(rows)} rows; billed {log['queries'][name]['billed_gb']} GB")
    (OUT / "bq_run_log.json").write_text(json.dumps(log, indent=1))


if __name__ == "__main__":
    main()
