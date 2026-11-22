# Frozen on the Last Open Version: How Dependent Libraries Respond When an Open-Source Supplier Relicenses

Taejun Oh (independent researcher, taejun.oh5@gmail.com). Working paper, November 2026.

When Lightbend moved new versions of Akka to the Business Source License in 2022, few of the open-source projects
built on Akka followed. This repository contains the paper, the dataset of dependents' choices, and the code that
reproduces every result in the paper.

| Folder | Content |
|---|---|
| `replication/paper/` | The paper (PDF and LaTeX source) |
| `dataset/` | The documented dataset: dependents of Akka and Elasticsearch, their release-level status, launch cohorts and motive codes (CC BY 4.0). See `dataset/README.md`. |
| `replication/` | Scripts, outputs and instructions to reproduce the results (code under MIT). See `replication/README.md`. |

The raw extracts used by the scripts (about 560 MB) are archived on Zenodo with the full replication package:
[doi:10.5281/zenodo.24440614](https://doi.org/10.5281/zenodo.24440614). See `replication/data/README.md`.

## Licence

Code: MIT. Dataset, derived tables and outputs: CC BY 4.0. The underlying package metadata comes from deps.dev
(Google Open Source Insights) and the package registries, chiefly Maven Central; see `LICENSE`.
