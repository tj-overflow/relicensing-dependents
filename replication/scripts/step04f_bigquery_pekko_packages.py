"""Step 4f: add packages that declare Pekko/Play-on-Pekko but never declared Akka.

Reason: projects often switch by publishing NEW artifacts (new groupId or artifact name), e.g.
Play 3 under org.playframework, which step04d's Akka-based candidate list cannot see.
Columns are kept minimal (no properties/dependencyManagement) to keep the scan small.
Outputs: data/raw/step04/bq_declared_pekko.jsonl, bq_versions_pekko.csv
Usage: python -I scripts/step04f_bigquery_pekko_packages.py --project <ID> [--run] [--max-gb 50]
"""
import argparse
import csv
import json
from pathlib import Path

from google.cloud import bigquery

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "step04"
DS = "bigquery-public-data.deps_dev_v1"
FAM = """(STARTS_WITH(x.Name, 'com.typesafe.akka:') OR STARTS_WITH(x.Name, 'com.lightbend.akka')
          OR STARTS_WITH(x.Name, 'org.apache.pekko:') OR STARTS_WITH(x.Name, 'com.typesafe.play:')
          OR STARTS_WITH(x.Name, 'org.playframework:'))"""
NEW = """(STARTS_WITH(x.Name, 'org.apache.pekko:') OR STARTS_WITH(x.Name, 'org.playframework:'))"""
OWN = "(STARTS_WITH(r.Name, 'org.apache.pekko:') OR STARTS_WITH(r.Name, 'com.typesafe.akka:') OR STARTS_WITH(r.Name, 'com.lightbend.akka'))"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--max-gb", type=float, default=50)
    a = ap.parse_args()
    c = bigquery.Client(project=a.project)
    snap = list(c.query(f"SELECT MAX(Time) t FROM `{DS}.Snapshots`").result())[0]["t"].isoformat()
    existing = {json.loads(l)["package"] for l in open(OUT / "bq_declared.jsonl", encoding="utf-8")}
    cands = f"""SELECT DISTINCT r.Name FROM `{DS}.MavenRequirements` r
        WHERE r.SnapshotAt = TIMESTAMP('{snap}') AND NOT {OWN}
          AND EXISTS(SELECT 1 FROM UNNEST(r.Dependencies) x WHERE {NEW})"""
    qs = {
        "bq_declared_pekko": f"""WITH cands AS ({cands})
            SELECT r.Name AS package, r.Version AS version,
                   ARRAY(SELECT AS STRUCT x.Name, x.Version, x.Scope, x.Type, x.Optional
                         FROM UNNEST(r.Dependencies) x WHERE {FAM}) AS deps
            FROM `{DS}.MavenRequirements` r JOIN cands c ON r.Name = c.Name
            WHERE r.SnapshotAt = TIMESTAMP('{snap}')""",
        "bq_versions_pekko": f"""WITH cands AS ({cands})
            SELECT v.Name AS package, v.Version AS version, v.UpstreamPublishedAt AS published,
                   ARRAY_TO_STRING(v.Licenses, ';') AS licences,
                   (SELECT l.URL FROM UNNEST(v.Links) l WHERE l.Label = 'SOURCE_REPO' LIMIT 1) AS source_repo,
                   v.VersionInfo.IsRelease AS is_release
            FROM `{DS}.PackageVersions` v JOIN cands c ON v.Name = c.Name
            WHERE v.SnapshotAt = TIMESTAMP('{snap}') AND v.System = 'MAVEN'""",
    }
    log = {"snapshot": snap}
    for name, q in qs.items():
        gb = c.query(q, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)).total_bytes_processed / 1e9
        print(f"{name}: estimated {gb:.2f} GB")
        log[name] = {"estimated_gb": round(gb, 3)}
        if not a.run or gb > a.max_gb:
            continue
        job = c.query(q)
        rows = list(job.result())
        log[name].update(billed_gb=round(job.total_bytes_billed / 1e9, 3), rows=len(rows))
        if name == "bq_versions_pekko":
            with open(OUT / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["package", "version", "published", "licences", "source_repo", "is_release"])
                for r in rows:
                    if r["package"] in existing:
                        continue
                    w.writerow([r["package"], r["version"], r["published"].isoformat() if r["published"] else "",
                                r["licences"], r["source_repo"] or "", r["is_release"]])
        else:
            with open(OUT / f"{name}.jsonl", "w", encoding="utf-8") as f:
                for r in rows:
                    if r["package"] in existing:
                        continue
                    f.write(json.dumps({"package": r["package"], "version": r["version"], "parent_name": None,
                                        "parent_version": None, "deps": [dict(d) for d in r["deps"]],
                                        "dm": [], "props": []}) + "\n")
        print(f"  wrote; billed {log[name]['billed_gb']} GB")
    (OUT / "bq_run_log_pekko.json").write_text(json.dumps(log, indent=1))


if __name__ == "__main__":
    main()
