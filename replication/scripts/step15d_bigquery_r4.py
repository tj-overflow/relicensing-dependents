"""Step 15d (R4): deps.dev BigQuery extracts for the non-competing benchmarks (C1) and downstream exposure (C2).

Benchmark selection and exposure rules as described in the paper, Sections 4-5 and 7. Same snapshot partition as Steps 4-9.
Stages (each one dry-runs first and runs only with --run and an estimate below --max-gb):
  candidates : PackageVersions only. Scala-suffixed Maven artifacts with a stable x.y.0 (y >= 1) release in
               [2019-05-06, 2020-05-06] or [2022-04-19, 2023-04-19]. Exclusions and the both-window rule are
               applied offline (step15e), which writes outputs/step15/r4_candidates.json.
  counts     : number of distinct dependent packages (non-test, non-optional) per candidate library, used to
               keep the 20 largest candidates for extraction (deviation recorded in Step 15c: an extraction
               cap, decided before any dependents were counted).
  bench      : declared versions of the kept candidates (plus Akka/Pekko, to drop overlap) in every release of
               every dependent package, and those packages' version dates and source repositories.
  exposure   : direct, non-test dependents of the packages of the Akka A24-A27 and Elasticsearch risk-set
               projects: dependent package, version, date and source repository (C2).
Outputs: data/raw/step15/<stage>*.{csv,jsonl}, data/raw/step15/bq_run_log.json
Usage: python -I scripts/step15d_bigquery_r4.py --project <ID> --stage <name> [--run] [--max-gb 40]
"""
import argparse
import csv
import json
from pathlib import Path

from google.cloud import bigquery

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "step15"
OUT.mkdir(parents=True, exist_ok=True)
DS = "bigquery-public-data.deps_dev_v1"
SNAP = "2026-11-02 21:00:03.179237+00:00"
SFX = r"_(2\.1[0-3]|3)$"
BASE = f"REGEXP_REPLACE(x.Name, r'{SFX}', '')"

Q = {
    "candidates": f"""
        SELECT v.Name AS package, v.Version AS version, v.UpstreamPublishedAt AS published
        FROM `{DS}.PackageVersions` v
        WHERE v.SnapshotAt = TIMESTAMP('{SNAP}') AND v.System = 'MAVEN'
          AND REGEXP_CONTAINS(v.Name, r'{SFX}')
          AND REGEXP_CONTAINS(v.Version, r'^[0-9]+\\.[1-9][0-9]*\\.0$')
          AND ((v.UpstreamPublishedAt >= TIMESTAMP('2019-05-06') AND v.UpstreamPublishedAt < TIMESTAMP('2020-05-07'))
            OR (v.UpstreamPublishedAt >= TIMESTAMP('2022-04-19') AND v.UpstreamPublishedAt < TIMESTAMP('2023-04-20')))""",
    "counts": f"""
        SELECT {BASE} AS library, COUNT(DISTINCT r.Name) AS dependents
        FROM `{DS}.MavenRequirements` r, UNNEST(r.Dependencies) x
        WHERE r.SnapshotAt = TIMESTAMP('{SNAP}') AND {BASE} IN UNNEST(@libs)
          AND IFNULL(LOWER(x.Scope), '') != 'test' AND IFNULL(LOWER(CAST(x.Optional AS STRING)), '') != 'true'
        GROUP BY library""",
    "bench_declared": f"""
        WITH cands AS (
          SELECT DISTINCT r.Name FROM `{DS}.MavenRequirements` r
          WHERE r.SnapshotAt = TIMESTAMP('{SNAP}')
            AND EXISTS(SELECT 1 FROM UNNEST(r.Dependencies) x WHERE {BASE} IN UNNEST(@libs)))
        SELECT r.Name AS package, r.Version AS version,
               ARRAY(SELECT AS STRUCT x.Name, x.Version, x.Scope, x.Optional FROM UNNEST(r.Dependencies) x
                     WHERE {BASE} IN UNNEST(@libs) OR STARTS_WITH(x.Name, 'com.typesafe.akka:')
                        OR STARTS_WITH(x.Name, 'com.lightbend.akka') OR STARTS_WITH(x.Name, 'org.apache.pekko:')) AS deps
        FROM `{DS}.MavenRequirements` r JOIN cands c ON r.Name = c.Name
        WHERE r.SnapshotAt = TIMESTAMP('{SNAP}')""",
    "bench_versions": f"""
        WITH cands AS (
          SELECT DISTINCT r.Name FROM `{DS}.MavenRequirements` r
          WHERE r.SnapshotAt = TIMESTAMP('{SNAP}')
            AND EXISTS(SELECT 1 FROM UNNEST(r.Dependencies) x WHERE {BASE} IN UNNEST(@libs)))
        SELECT v.Name AS package, v.Version AS version, v.UpstreamPublishedAt AS published,
               (SELECT l.URL FROM UNNEST(v.Links) l WHERE l.Label = 'SOURCE_REPO' LIMIT 1) AS source_repo
        FROM `{DS}.PackageVersions` v JOIN cands c ON v.Name = c.Name
        WHERE v.SnapshotAt = TIMESTAMP('{SNAP}') AND v.System = 'MAVEN'""",
    "exposure": f"""
        WITH hits AS (
          SELECT r.Name AS package, r.Version AS version,
                 ARRAY(SELECT DISTINCT x.Name FROM UNNEST(r.Dependencies) x
                       WHERE x.Name IN UNNEST(@pkgs) AND IFNULL(LOWER(x.Scope), '') != 'test') AS targets
          FROM `{DS}.MavenRequirements` r
          WHERE r.SnapshotAt = TIMESTAMP('{SNAP}')
            AND EXISTS(SELECT 1 FROM UNNEST(r.Dependencies) x
                       WHERE x.Name IN UNNEST(@pkgs) AND IFNULL(LOWER(x.Scope), '') != 'test'))
        SELECT h.package, h.version, h.targets, v.UpstreamPublishedAt AS published,
               (SELECT l.URL FROM UNNEST(v.Links) l WHERE l.Label = 'SOURCE_REPO' LIMIT 1) AS source_repo
        FROM hits h LEFT JOIN `{DS}.PackageVersions` v
          ON v.Name = h.package AND v.Version = h.version
         AND v.SnapshotAt = TIMESTAMP('{SNAP}') AND v.System = 'MAVEN'""",
}
STAGES = {"candidates": ["candidates"], "counts": ["counts"], "bench": ["bench_declared", "bench_versions"],
          "exposure": ["exposure"]}


def params(name, dry):
    """Array parameters. Bytes scanned do not depend on the list, so a dry run may use a placeholder;
    a real run requires the list file written by step15e."""
    if name == "candidates":
        return []
    f = ROOT / "outputs/step15" / ("r4_exposure_packages.json" if name == "exposure" else "r4_candidates.json")
    key = {"counts": "libraries", "exposure": "packages"}.get(name, "extract")
    vals = json.loads(f.read_text()).get(key) if f.exists() else None
    if not vals:
        if not dry:
            raise SystemExit(f"{name}: {f.name} (key '{key}') is missing; run step15e first")
        vals = ["placeholder.group:placeholder"]
    return [bigquery.ArrayQueryParameter("pkgs" if name == "exposure" else "libs", "STRING", vals)]


def write(name, rows):
    if name in ("bench_declared",):
        with open(OUT / f"{name}.jsonl", "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps({"package": r["package"], "version": r["version"],
                                    "deps": [dict(d) for d in r["deps"]]}) + "\n")
        return
    with open(OUT / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        keys = list(rows[0].keys()) if rows else []
        w.writerow(keys)
        for r in rows:
            w.writerow([";".join(v) if isinstance(v, list) else (v.isoformat() if hasattr(v, "isoformat") else v)
                        for v in (r[k] for k in keys)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--stage", required=True, choices=list(STAGES) + ["all"])
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--max-gb", type=float, default=40)
    a = ap.parse_args()
    c = bigquery.Client(project=a.project)
    logf = OUT / "bq_run_log.json"
    log = json.loads(logf.read_text()) if logf.exists() else {"snapshot": SNAP}
    names = [n for s in (STAGES if a.stage == "all" else [a.stage]) for n in STAGES[s]]
    for name in names:
        cfg = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False, query_parameters=params(name, True))
        gb = c.query(Q[name], job_config=cfg).total_bytes_processed / 1e9
        print(f"{name}: estimated {gb:.2f} GB", flush=True)
        log.setdefault(name, {})["estimated_gb"] = round(gb, 3)
        if not a.run or gb > a.max_gb:
            continue
        job = c.query(Q[name], job_config=bigquery.QueryJobConfig(query_parameters=params(name, False)))
        rows = list(job.result())
        log[name].update(billed_gb=round(job.total_bytes_billed / 1e9, 3), rows=len(rows), job_id=job.job_id)
        write(name, rows)
        print(f"  wrote {len(rows)} rows; billed {log[name]['billed_gb']} GB", flush=True)
    logf.write_text(json.dumps(log, indent=1))


if __name__ == "__main__":
    main()
