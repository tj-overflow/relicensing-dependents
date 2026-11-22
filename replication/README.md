# Replication package

*Frozen on the Last Open Version: How Dependent Libraries Respond When an Open-Source Supplier Relicenses* (Oh, 2026).

This package contains the data and code needed to reproduce every result reported in the paper. It is archived on Zenodo ([doi:10.5281/zenodo.24440614](https://doi.org/10.5281/zenodo.24440614)); the GitHub repository (https://github.com/TJ-overflow/relicensing-dependents) holds the same files except the raw extracts in `data/raw/`.

## What is here

| Folder | Content |
|---|---|
| `scripts/` | Every script, named by research step (`stepNN…`). Each docstring states inputs, outputs and any external access. |
| `data/raw/` | Extracts from deps.dev BigQuery (snapshot 2026-11-02), the deps.dev API, Maven Central and the GitHub API, with the exclusions listed below |
| `outputs/` | Every intermediate and final output, by step |
| `paper/` | LaTeX source, bibliography and compiled PDF |
| `sources/` | Event register for the chronology (Step 3) |
| `validation/` | The author's blind human codes for the 60-repository text-validation sample (codes only; the free-text notes are removed) |

The large Step 15 extracts (`data/raw/step15/*.gz`) are gzipped. The scripts read the `.gz` files directly.

**Excluded, with how to rebuild each one:**

| Excluded | Why | Rebuild with |
|---|---|---|
| Cached POM files (`data/raw/step0x/poms`) | Large (about 1.1 GB) and re-fetchable | `step08b`, `step09b` (Maven Central, paced at 1 request per second) |
| Repository build files (`data/raw/step05/build_files`, `step09/build_files`) | Third-party code | `step05b`, `step09d` |
| Issue and pull-request text (`data/raw/step12/issues`, `outputs/step12/text_*`) | Third-party text | `step12z` (GitHub search API), then `step12b` and `step12b2` |
| GitHub profile fields | Personal data | `owners.json` keeps only login and account type, which is all the scripts use |
| Archived vendor web pages (`data/raw/wayback`) | Third-party copyright | `step03c` (Internet Archive) |
| The human-coding page (`validation/human_coding.html`) | It embeds issue text | `step14c_validation_packet.py`, after rebuilding the issue text |

## Software

- Python 3.12.10 with the packages in `requirements.txt`.
- R 4.5.2 with HonestDiD 0.2.8, for `step13e_honestdid.R`.
- The paper was compiled with TeX Live 2026 (`latexmk -pdf paper.tex`).

## Re-running the analysis (offline)

```
pip install -r requirements.txt
python run_all.py --rscript "<path to Rscript>"
```

`run_all.py` runs Steps 11 to 16 in order from the included data and rewrites `outputs/`.

**Run time and seeds.**
- A full run takes about 2 h 40 min on a Windows laptop. About 2 h 33 min of that is the HonestDiD breakdown grids (`step13e_honestdid.R`); every other step takes under 2.5 min.
- The test run of November 17 reproduced every output. Four Step 11-12 files can differ in key, row or column order between runs (Python set iteration); their values are identical. PDF figures differ only in their creation date.
- Seeds are fixed in the scripts:
  - 20261110 for Step 13;
  - 20261111 for the launch design;
  - 20261112 for the Step 15 bootstraps.

**Not re-run by `run_all.py`.**
- The Step 12 text steps (`step12b`, `step12b2`, `step12c`) and the Step 14 coding page (`step14c`). They need the excluded issue text.
- The BigQuery extraction for Step 15 (`step15d_bigquery_r4.py`).

**Where the reported numbers are:**

| Results | File |
|---|---|
| Figure 1, outcomes at each launch | `outputs/step15/fig_outcomes_data.csv` |
| Within-Akka contrasts, Lee bounds, four-way outcomes (paper Section 5, Table 3) | `outputs/step15/launch_estimates.json`, `fourway_shares.csv` |
| Benchmarks, including the non-competing ones (Table 4) | `outputs/step15/r4_estimates.json` (`C1`), `bench_shares.csv`, `r4_benchmarks.json` |
| Typelevel launch design and Kaplan-Meier curves | `outputs/step13/lu/estimates.json`, `shares.csv`, `km.csv` |
| Panel estimate and its robustness (Section 6) | `outputs/step11/estimates.json`, `outputs/step13/robustness.json`, `outputs/step13/honestdid.csv` |
| Freeze count among active non-adopters | `outputs/step15/freeze_count.json` |
| Mechanisms and exposure test (Section 7) | `outputs/step11/descriptives.json`, `outputs/step12/*.json`, `outputs/step15/r4_estimates.json` (`C2`) |
| Human validation of the text codes | `outputs/step14/validation_results.json` |
| Repository tag check for inactive and frozen projects (Section 8) | `outputs/step16/tag_check.json`, `tag_check.csv` |

## Re-collecting the data

The collection scripts need credentials and network access. Run them in step order; each one's docstring gives its usage.

| Source | Scripts | Notes |
|---|---|---|
| deps.dev BigQuery | `step04d`, `step04f`, `step06a`, `step07p_bigquery_elastic`, `step08a`, `step09a`, `step12e`, `step15d_bigquery_r4` | Every query reads the snapshot partition `2026-11-02 21:00:03.179237+00:00`. About 415 GB were billed in total, including 45 GB for Step 15. Each script takes `--max-gb` as a hard cap. `step15d` runs in stages, with `step15e_r4_lists.py` between them. |
| deps.dev documented API | `step03`, `step03b`, `step04c`, `step06b`, `step07a`, `step08c` | Release dates and licences |
| Maven Central | `step08b`, `step09b` | Parent POMs; sequential, at 1 request per second |
| GitHub REST and search API | `step05b`, `step05d`, `step09d`, `step11z`, `step12z` | Unauthenticated, paced (1 request per minute for users, 7 seconds for search) |
| GitHub repositories (git protocol) | `step16a_tag_check` | `git ls-remote --tags`, sequential, 1 request per second |
| Internet Archive | `step03c` | |

`step04a` and `step04b` are superseded by the BigQuery route and are not needed. Their partial output from an undocumented endpoint was discarded.

## Data licence and attribution

- **Code.** The scripts and `run_all.py` are released under the MIT licence (see `LICENSE`).
- **Derived tables and outputs.** Released under CC BY 4.0. Please cite the paper and credit deps.dev (Google Open Source Insights) and Maven Central.
- **Raw extracts (`data/raw/`).** These are query results from deps.dev and records from the GitHub API, Maven Central and the deps.dev API. deps.dev states that the data it generates are available under CC BY 4.0. The underlying package metadata originates from the package registries, chiefly Maven Central, and remains subject to their own terms. No POM files are redistributed.
- The public dataset (`../dataset`) is the documented subset for reuse.
