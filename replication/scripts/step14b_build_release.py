"""Step 14b: assemble the public dataset (release/dataset) and the replication staging folder (release/replication).

Nothing is uploaded. The folders are built locally for the author to review before any deposit.

Dataset tables (release/dataset):
  events.csv                 the two relicensing events and their dated milestones (from the Step 3 and Step 8 notes)
  fork_ports.csv             first stable fork (Pekko) release of each Akka-family artifact (outputs/step07/port_dates.csv)
  akka_dependents.csv        Akka risk set v2, project level (outputs/step05/risk_set_v2.csv + port timing)
  es_dependents.csv          Elasticsearch risk set, project level (outputs/step08/es_risk_set.csv)
  akka_release_status.csv    release-level coded status of every risk-set artifact release (outputs/step04/project_panel.csv)
  es_release_status.csv      same for Elasticsearch (outputs/step08/es_project_panel.csv)
  launch_cohorts.csv         launch cohorts A24-A27 and Typelevel (outputs/step13/lu/cohorts.csv + cohorts_a24.csv)
  benchmark_cohorts.csv      non-competing benchmark cohorts (outputs/step15/bench_cohorts.csv)
  downstream_exposure.csv    direct downstream packages per Akka launch-cohort project (outputs/step15/exposure_projects.csv)
  text_motive_codes.csv      repository-level motive codes (model-coded; validated on a 60-unit sample); no text
  text_validation_human.csv  the author's blind human codes for the 60-unit validation sample (codes only, no notes)
  owner_types.csv            GitHub owner login and account type only (no profile fields)
Replication staging (Step 15 additions): large Step 15 extracts are shipped gzipped; the human validation codes are
shipped without the free-text note column; the coding page (which embeds issue text) is not shipped.
The replication package holds only what is needed to reproduce the paper's results: data, scripts, outputs, the
event register and the final paper. Other workspace files are not shipped.
Excluded from both folders: issue and pull-request text, GitHub profile fields, archived vendor web pages (hashes are
kept), cached POM files (re-fetchable), and the abandoned undocumented-endpoint output.
"""
import csv
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REL = ROOT / "release"
DS, RP = REL / "dataset", REL / "replication"
DS.mkdir(parents=True, exist_ok=True)
for p in DS.glob("*.csv"):  # README.md and CITATION.cff are hand-written and kept
    p.unlink()
for p in list(RP.glob("*")) if RP.exists() else []:  # replication README, run_all.py, requirements are kept
    if p.is_dir():
        shutil.rmtree(p)
RP.mkdir(parents=True, exist_ok=True)

EVENTS = [
    # event, milestone, date, detail
    ("akka", "last_open_release", "2022-09-06", "Akka core 2.6.20 and HTTP 10.2.10, Apache-2.0"),
    ("akka", "announcement", "2022-09-07", "New versions under BUSL-1.1 (Business Source License 1.1)"),
    ("akka", "first_restricted_artifact", "2022-09-09", "2.7.0-M1 (milestone)"),
    ("akka", "first_restricted_stable", "2022-10-19", "Core 2.7.0 and HTTP 10.4.0"),
    ("akka", "fork_first_stable", "2023-07-10", "Apache Pekko core 1.0.0 (based on Akka 2.6.20)"),
    ("akka", "last_open_patch", "2023-06-21", "2.6.21, critical TLS fix"),
    ("akka", "open_line_end_of_life", "2023-09", "End of 2.6 and HTTP 10.2 patches"),
    ("akka", "licence_keys", "2024-10-01", "New versions require a license key for production use"),
    ("akka", "first_change_date", "2025-10-19", "2.7.0 and HTTP 10.4.0 revert to Apache-2.0 (three years after release)"),
    ("elasticsearch", "announcement", "2021-01-14", "New versions under ELv2 / SSPL"),
    ("elasticsearch", "last_open_release", "2021-01-15", "7.10.2, Apache-2.0"),
    ("elasticsearch", "first_restricted_stable", "2021-02-10", "7.11.0"),
    ("elasticsearch", "fork_first_stable", "2021-07-12", "OpenSearch 1.0 GA (Maven artifacts 2021-08-27)"),
    ("elasticsearch", "vendor_apache_client", "2021-09-30", "co.elastic.clients:elasticsearch-java 7.15.0"),
    ("elasticsearch", "agpl_option_announced", "2024-08-29", "AGPL added as a license option"),
    ("elasticsearch", "first_agpl_release", "2024-11-12", "8.16.0"),
]
SCOPE = {"akka": ("Apache-2.0", "BUSL-1.1", "users: commercial production use (free license below US$25M revenue in 2022)",
                  "Apache Pekko"),
         "elasticsearch": ("Apache-2.0", "ELv2;SSPL-1.0", "competitors: providing the software as a hosted or managed service",
                           "OpenSearch")}
with open(DS / "events.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["event", "old_licence", "new_licence", "restriction_scope", "fork", "milestone", "date", "detail"])
    for ev, ms, d, det in EVENTS:
        w.writerow([ev, *SCOPE[ev], ms, d, det])


def copy_cols(src, dst, cols=None, rename=None, drop=None):
    with open(src, encoding="utf-8") as fi, open(dst, "w", newline="", encoding="utf-8") as fo:
        r = csv.DictReader(fi)
        keep = [c for c in (cols or r.fieldnames) if c not in (drop or [])]
        w = csv.DictWriter(fo, fieldnames=[(rename or {}).get(c, c) for c in keep])
        w.writeheader()
        n = 0
        for row in r:
            w.writerow({(rename or {}).get(c, c): row[c] for c in keep})
            n += 1
    return n


counts = {}
counts["fork_ports"] = copy_cols(ROOT / "outputs/step07/port_dates.csv", DS / "fork_ports.csv")
# Akka dependents: risk set v2 plus port timing
tdates = {r["project"]: r for r in csv.DictReader(open(ROOT / "outputs/step07/treatment_dates.csv", encoding="utf-8"))}
src = list(csv.DictReader(open(ROOT / "outputs/step05/risk_set_v2.csv", encoding="utf-8")))
cols = ["project", "owner", "vendor", "foundation", "n_artifacts", "n_pre_releases", "n_post_releases", "active_post",
        "outcome_v2", "first_switch_v2", "first_bsl", "ever_upgraded_bsl", "own_licence_pre", "own_licence_changed",
        "scala3_pre_event", "play_user_pre", "akka_provided_or_testkit_only", "akka_modules_pre"]
with open(DS / "akka_dependents.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=cols + ["all_ported_date"])
    w.writeheader()
    for r in src:
        w.writerow({**{c: r[c] for c in cols}, "all_ported_date": tdates.get(r["project"], {}).get("T_all", "")})
counts["akka_dependents"] = len(src)
counts["es_dependents"] = copy_cols(ROOT / "outputs/step08/es_risk_set.csv", DS / "es_dependents.csv")
counts["akka_release_status"] = copy_cols(ROOT / "outputs/step04/project_panel.csv", DS / "akka_release_status.csv")
counts["es_release_status"] = copy_cols(ROOT / "outputs/step08/es_project_panel.csv", DS / "es_release_status.csv")
counts["launch_cohorts"] = copy_cols(ROOT / "outputs/step13/lu/cohorts.csv", DS / "launch_cohorts.csv")
with open(DS / "launch_cohorts.csv", "a", newline="", encoding="utf-8") as fo:  # append A24 (same columns)
    rr = list(csv.DictReader(open(ROOT / "outputs/step13/lu/cohorts_a24.csv", encoding="utf-8")))
    hdr = next(csv.reader(open(DS / "launch_cohorts.csv", encoding="utf-8")))
    csv.DictWriter(fo, fieldnames=hdr).writerows(rr)
    counts["launch_cohorts"] += len(rr)
counts["benchmark_cohorts"] = copy_cols(ROOT / "outputs/step15/bench_cohorts.csv", DS / "benchmark_cohorts.csv")
counts["downstream_exposure"] = copy_cols(ROOT / "outputs/step15/exposure_projects.csv", DS / "downstream_exposure.csv")
HUMAN = ROOT / "validation/human_codes_coder.csv"
counts["text_validation_human"] = copy_cols(HUMAN, DS / "text_validation_human.csv", drop=["note", "coder"])
counts["text_motive_codes"] = copy_cols(ROOT / "outputs/step12/text_coded_projects.csv", DS / "text_motive_codes.csv",
                                        cols=["event", "repo", "R", "codes", "action"], rename={"R": "relevant"})
own = json.load(open(ROOT / "data/raw/step11/owners.json", encoding="utf-8"))
with open(DS / "owner_types.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["owner", "type"])
    for k, v in sorted(own.items()):
        w.writerow([k, (v or {}).get("type", "") if isinstance(v, dict) else ""])
counts["owner_types"] = len(own)
shutil.copy(ROOT / "outputs/step12/text_codebook.md", DS / "text_codebook.md")

# ---------- replication staging ----------
EXCLUDE_DIRS = {"poms", "build_files", "issues", "abandoned_web_endpoint", "wayback", "__pycache__"}
EXCLUDE_FILES = {"owners.json", "text_corpus.csv", "text_for_coding.txt", "text_for_coding_projects.txt",
                 "text_project_items.csv", "text_validation_sample.csv", "text_keyword.csv",
                 # Step 15 extracts shipped gzipped instead (below)
                 "bench_declared.jsonl", "bench_versions.csv", "exposure.csv", "candidates.csv"}
GZIP = ["bench_declared.jsonl", "bench_versions.csv", "exposure.csv", "candidates.csv"]


def copytree(src, dst):
    n = 0
    for p in src.rglob("*"):
        rel = p.relative_to(src)
        if any(part in EXCLUDE_DIRS for part in rel.parts) or p.name in EXCLUDE_FILES or p.name.endswith("_freeze.json") or p.is_dir():
            continue
        q = dst / rel
        q.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, q)
        n += 1
    return n


counts["replication_files"] = {d: copytree(ROOT / d, RP / d) for d in ("scripts", "data", "outputs", "sources")}
# paper: final source, bibliography and PDF only (no earlier versions, build files or working notes)
(RP / "paper").mkdir(exist_ok=True)
for name in ("paper.tex", "references.bib", "paper.pdf"):
    shutil.copy2(ROOT / "paper" / name, RP / "paper" / name)
counts["replication_files"]["paper"] = 3
import gzip  # noqa: E402
for name in GZIP:
    with open(ROOT / "data/raw/step15" / name, "rb") as fi, gzip.open(RP / "data/raw/step15" / (name + ".gz"), "wb", 6) as fo:
        shutil.copyfileobj(fi, fo)
(RP / "validation").mkdir(exist_ok=True)
copy_cols(HUMAN, RP / "validation/human_codes_coder.csv", drop=["note"])
# owner types without profile fields, for step11 scripts
(RP / "data/raw/step11").mkdir(parents=True, exist_ok=True)
json.dump({k: {"login": k, "type": (v or {}).get("type") if isinstance(v, dict) else None} for k, v in own.items()},
          open(RP / "data/raw/step11/owners.json", "w", encoding="utf-8"), indent=0)
# manifest with hashes
man = []
for base in (DS, RP):
    for p in sorted(base.rglob("*")):
        if p.is_file():
            man.append(dict(path=str(p.relative_to(REL)).replace("\\", "/"), bytes=p.stat().st_size,
                            sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
(REL / "MANIFEST.json").write_text(json.dumps(dict(counts=counts, files=man), indent=1))
print(json.dumps(counts, indent=1))
print("total MB", round(sum(m["bytes"] for m in man) / 1e6, 1))
