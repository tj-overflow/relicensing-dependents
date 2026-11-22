# Dependents of Relicensed Open-Source Suppliers: Akka (BSL, 2022) and Elasticsearch (ELv2, 2021)

Version 1.0 (November 2026). Archived on Zenodo: [doi:10.5281/zenodo.24440614](https://doi.org/10.5281/zenodo.24440614).

This dataset records what downstream Maven projects did after two open-source suppliers moved new versions to non-OSI licenses:
- **Akka.** Moved from Apache-2.0 to BUSL-1.1 in September 2022. Its fork is Apache Pekko.
- **Elasticsearch.** Moved from Apache-2.0 to ELv2/SSPL in January 2021. Its fork is OpenSearch.

The dataset covers every package in the deps.dev Maven snapshot of 2026-11-02 that ever declared the supplier. For each one, every release is coded by the supplier versions it declares, and each project gets an outcome at a fixed horizon. The dataset accompanies the working paper *Frozen on the Last Open Version* (Oh, 2026).

## Files

| File | Rows | Unit | Content |
|---|---|---|---|
| `events.csv` | 16 | event milestone | Licenses, restriction scope, fork, and dated milestones of the two events |
| `fork_ports.csv` | 144 | Akka-family artifact | First stable Pekko (or Play 3) release that substitutes for each Akka-family artifact declared by the risk set |
| `akka_dependents.csv` | 427 | project | Akka risk set: activity, outcome at 2025-09-30, dates of the first switch and first BSL adoption, pre-event flags, date all needed ports existed |
| `akka_release_status.csv` | 147,671 | artifact release | Status of every release of every risk-set artifact |
| `es_dependents.csv` | 329 | project | Elasticsearch risk set and the vendor-only control: activity, outcomes at 2024-11 and 2025-09, first OpenSearch / restricted / vendor-client dates |
| `es_release_status.csv` | 19,089 | artifact release | Status of every release of every Elasticsearch risk-set artifact in the window, with the families declared |
| `launch_cohorts.csv` | 1,370 | project × launch cohort | Launch design: Akka 2.4, 2.5, 2.6, 2.7 and the cats-effect / fs2 launches; covariates, adoption and post-launch status |
| `benchmark_cohorts.csv` | 1,521 | project × benchmark cohort | Non-competing benchmark libraries (20 extracted; cats-core and jackson-module-scala kept), same rules and columns |
| `downstream_exposure.csv` | 903 | project × Akka cohort | Number of distinct packages outside the project that declared one of its packages as a direct dependency in the year before launch |
| `text_motive_codes.csv` | 135 | repository | Motive codes from the repository's own issues and pull requests, model-coded and validated on a 60-repository sample. No text is included. |
| `text_validation_human.csv` | 60 | repository | The author's blind human codes for the validation sample (codes and action only) |
| `text_codebook.md` | | | Codebook for the motive codes |
| `owner_types.csv` | 298 | GitHub owner | Account type (Organization or User) only |

## Definitions

- **Project.** The normalized GitHub repository (`github.com/owner/repo`, lower case) from the package's source-repository link. Packages without one are grouped by Maven groupId (`maven:<groupId>`). Two moved repositories are merged (Eclipse Ditto, neotypes).
- **Declared versions.** Versions come from the published POM, not the resolved build. Declarations come from the dependencies, dependencyManagement, properties and parent chain. Test-scope and optional dependencies are ignored when coding status. Declared versions that are not on Maven Central (Akka 2.9 and later) count as restricted.
- **Akka release status** (`akka_release_status.status`):
  - `akka_open`: declares Akka versions under Apache-2.0.
  - `akka_bsl`: declares a BUSL-1.1 version, or 2.9 and later.
  - `pekko`: declares Pekko.
  - `akka_unresolved`: the version could not be resolved.
  - `none`: no Akka-family declaration.
- **Akka outcome at the horizon** (`akka_dependents.outcome_v2`). This is taken from the artifacts still maintained at 2025-09-30, meaning those with a last release within six months of the project's last release:
  - `switch`: Pekko only.
  - `dual_or_partial`: both Akka and Pekko artifacts maintained.
  - `upgrade`: BSL Akka.
  - `freeze`: Apache Akka only.
  - `removed`: neither.
  - `no_release`: no release after 2022-09-07.
- **Risk set (Akka).** Projects with at least one release between 2020-09-07 and 2022-09-06 where the latest pre-event release of at least one artifact declares a non-test, non-optional Akka dependency. Vendor-owned projects are flagged (`vendor = 1`) and excluded from the paper's estimates.
- **Elasticsearch status** (`es_release_status.status`): `upgrade`, `upgrade_agpl`, `freeze`, `switch`, `dual`, `vendor_open`, `removed`, `spring_only` or `es_version_unresolved`. The `kinds` column lists the declared families:
  - `es_open`, `es_restricted`, `es_agpl`;
  - `vendor_new_client` (Elastic's Apache Java client);
  - `spring_data`.
- **Launch cohorts** (`launch_cohorts.csv`).
  - Cohorts: A24 (Akka 2.4.0, 2015-09-30), A25 (2.5.0, 2017-04-12), A26 (2.6.0, 2019-11-06), A27 (2.7.0, 2022-10-19, BSL), F21/C21 (fs2 2.1.0, cats-effect 2.1.0), F34/C34 (fs2 3.4.0, cats-effect 3.4.0).
  - `st240`, `old240`, `pk240` (and the 365-day versions): the declared status of the last release in the window, whether any release still declared the previous series, and whether any declared Pekko. Together with `adopt_days` and `act240` they give the four outcomes in the paper: adopted, kept the previous series, left (fork or no Akka), no release.
  - `y1`: adopted the new series within 240 days, among projects active in that window.
  - `y1u`: the same, over the whole risk set.
  - `y1_365`: adoption within 365 days.
  - `y2`: A27 only; left 2.6 for 2.7 or later, or for Pekko, within 365 days.
  - `adopt_days`: days to the first adopting release.
  - `last_rel_days`: days to the last release within 365 days.
  - Covariates are measured over the year before launch.
  - The design is documented in the paper, Section 5.
- **Motive codes.** One row per repository, from up to four items chosen by a fixed rule. Codes:
  - `LEGAL_OWN`, `LEGAL_USERS`, `LICENCE_UNSPEC`;
  - `TRUST`, `COMPAT`, `AGEING`, `COORD`, `COST`;
  - `USER_REQUEST`;
  - see the codebook.

  `action` is the stated action. The codes were assigned by a language model (Claude Opus 5.5, used interactively on 2026-11-10). The author coded a 60-repository sample blind to the model's codes (`text_validation_human.csv`). The acceptance threshold was κ ≥ 0.60 on both codes; agreement was κ = 0.90 for "license given as a reason" and κ = 0.80 for `COMPAT`. Agreement on relevance was lower (κ = 0.35), because the model counted routine version bumps inside the fork as relevant.

## Validation

- **Akka.** The registry coding was checked against the projects' own build files for a stratified sample: 94.7% raw agreement, Cohen's κ = 0.93.
- **Elasticsearch.** κ = 0.85 under the registry rule.
- **Known blind spot.** Projects that shade the supplier inside their own artifact are coded `removed` (for example Apache Flink).

## Sources and license

- **Package metadata and declared dependencies.** deps.dev (Google Open Source Insights) BigQuery dataset, snapshot 2026-11-02. deps.dev states that the data it generates are available under CC BY 4.0. The underlying package metadata (for example the POM content and publication dates of Maven Central packages) originates from the package registries, chiefly Maven Central, and remains subject to their own terms. Fork port dates and supplier release dates also come from deps.dev.
- **Owner types.** GitHub REST API. Only the account type is included.
- **Motive codes.** Derived from public GitHub issues and pull requests. The text itself is not redistributed; the repositories are public and can be re-queried with the search script in the replication package.
- **License.** The tables in this dataset are the author's derived coding and are released under **CC BY 4.0** (see `LICENSE`). Please cite the working paper and credit deps.dev (Google Open Source Insights) and Maven Central as the sources of the underlying package data. No raw registry files (such as POM files) are included.
- **Personal data.** The tables contain GitHub owner and repository names as they appear in public package metadata. To have a project removed, contact the author (taejun.oh5@gmail.com).

## Citation

Oh, Taejun (2026). *Dependents of Relicensed Open-Source Suppliers: Akka and Elasticsearch* (dataset, version 1.0). Zenodo. https://doi.org/10.5281/zenodo.24440614. Accompanies "Frozen on the Last Open Version: How Dependent Libraries Respond When an Open-Source Supplier Relicenses", working paper.
