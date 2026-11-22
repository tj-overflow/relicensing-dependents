"""Step 9a: dependents of the Elasticsearch comparison libraries (SolrJ, Lucene core, HBase client) from
deps.dev BigQuery. Rule fixed in outputs/step09/comparison_rule.md before this extraction.

Same snapshot and method as step08a: declared dependencies, dependencyManagement, filtered properties and
parent coordinates (bq_cmp_declared), plus publication dates and source repositories (bq_cmp_versions).
Extracted dependency families: the three comparison libraries plus Elasticsearch/OpenSearch (overlap).
Parent POMs are resolved from Maven Central in step09b (free).
Usage: python -I scripts/step09a_bigquery_comparison.py --project <ID> {dryrun,run} [--max-gb 80] [--only q1,q2]
Outputs (data/raw/step09/): bq_cmp_declared.jsonl, bq_cmp_versions.csv, bq_run_log.json
"""
import argparse
import csv
import json
from pathlib import Path

from google.cloud import bigquery

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "step09"
OUT.mkdir(parents=True, exist_ok=True)
DS = "bigquery-public-data.deps_dev_v1"
SNAP = "2026-11-02 21:00:03.179237+00:00"  # same partition as Steps 4-8

CMP = """(x.Name = 'org.apache.solr:solr-solrj' OR x.Name = 'org.apache.lucene:lucene-core'
          OR x.Name = 'org.apache.hbase:hbase-client')"""
FAM = CMP[:-1] + """ OR STARTS_WITH(x.Name, 'org.elasticsearch') OR STARTS_WITH(x.Name, 'co.elastic.clients:')
          OR STARTS_WITH(x.Name, 'org.opensearch'))"""
OWN = """(STARTS_WITH(r.Name, 'org.apache.solr:') OR STARTS_WITH(r.Name, 'org.apache.lucene:')
          OR STARTS_WITH(r.Name, 'org.apache.hbase:'))"""
PROPS = r"REGEXP_CONTAINS(LOWER(p.Name), r'solr|lucene|hbase|elastic|opensearch|spring')"
CANDS = f"""SELECT DISTINCT r.Name FROM `{DS}.MavenRequirements` r
    WHERE r.SnapshotAt = TIMESTAMP('{SNAP}') AND NOT {OWN}
      AND (EXISTS(SELECT 1 FROM UNNEST(r.Dependencies) x WHERE {CMP})
           OR EXISTS(SELECT 1 FROM UNNEST(r.DependencyManagement) x WHERE {CMP}))"""
QS = {
    "bq_cmp_declared": f"""WITH cands AS ({CANDS})
        SELECT r.Name AS package, r.Version AS version,
               r.Parent.Name AS parent_name, r.Parent.Version AS parent_version,
               ARRAY(SELECT AS STRUCT x.Name, x.Version, x.Scope, x.Type, x.Optional
                     FROM UNNEST(r.Dependencies) x WHERE {FAM}) AS deps,
               ARRAY(SELECT AS STRUCT x.Name, x.Version, x.Scope, x.Type
                     FROM UNNEST(r.DependencyManagement) x WHERE {FAM}) AS dm,
               ARRAY(SELECT AS STRUCT p.Name, p.Value FROM UNNEST(r.Properties) p WHERE {PROPS}) AS props
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
    ap.add_argument("mode", choices=["dryrun", "run"])
    ap.add_argument("--max-gb", type=float, default=80)
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    c = bigquery.Client(project=a.project)
    f = OUT / "bq_run_log.json"
    log = json.loads(f.read_text()) if f.exists() else {"snapshot": SNAP}
    for name, q in QS.items():
        if a.only and name not in a.only.split(","):
            continue
        gb = c.query(q, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)).total_bytes_processed / 1e9
        print(f"{name}: estimated {gb:.2f} GB", flush=True)
        log[name] = {"estimated_gb": round(gb, 3)}
        if a.mode != "run" or gb > a.max_gb:
            continue
        job = c.query(q)
        rows = list(job.result())
        log[name].update(billed_gb=round(job.total_bytes_billed / 1e9, 3), rows=len(rows), job_id=job.job_id)
        if name == "bq_cmp_versions":
            with open(OUT / f"{name}.csv", "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(["package", "version", "published", "licences", "source_repo", "is_release"])
                for r in rows:
                    w.writerow([r["package"], r["version"], r["published"].isoformat() if r["published"] else "",
                                r["licences"], r["source_repo"] or "", r["is_release"]])
        else:
            with open(OUT / f"{name}.jsonl", "w", encoding="utf-8") as fh:
                for r in rows:
                    fh.write(json.dumps({k: (list(map(dict, v)) if isinstance(v, list) else v)
                                         for k, v in r.items()}) + "\n")
        print(f"  wrote {len(rows)} rows; billed {log[name]['billed_gb']} GB", flush=True)
    f.write_text(json.dumps(log, indent=1))


if __name__ == "__main__":
    main()
