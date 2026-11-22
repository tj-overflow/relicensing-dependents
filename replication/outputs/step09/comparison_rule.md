# Step 9 comparison rule (Elasticsearch replication)

Fixed on November 8, 2026, before any comparison-library dependent data was extracted. It mirrors the Step 6 rule for Akka.

## Which suppliers count as comparison libraries

A supplier library is a comparison library if it meets all of the following:

1. **Same function, same users.** It is a Java client or engine library for a search or data-storage system, used by the same Java back-end developer population as Elasticsearch.
2. **Structurally stable licence.** It is an Apache Software Foundation top-level project: Apache-2.0 under ASF governance, which bars a move to a non-OSI licence. Governance and Maven coordinates are unchanged from 2019 to 2025.
3. **Actively released.** It has at least one release in each year 2019-2025. This was checked from deps.dev before extraction.
4. **Not part of the Elasticsearch or OpenSearch distribution.**
5. **Common support.** It has at least 50 direct dependent projects in the pre-event window. This is checked after extraction. A library that fails is dropped. The rule concerns support, not outcomes.

**Candidates meeting rules 1-4:**

| Library | Releases 2019-2025 (per year) | Notes |
|---|---|---|
| SolrJ (`org.apache.solr:solr-solrj`) | 11, 10, 8, 3, 5, 7, 4 | The closest substitute: a search-server client |
| Lucene core (`org.apache.lucene:lucene-core`) | 11, 10, 9, 7, 6, 10, 8 | Embedded search engine. Its users parallel Elasticsearch's server-jar (plugin or embedded) users |
| HBase client (`org.apache.hbase:hbase-client`) | 21, 13, 19, 12, 14, 11, 12 | Data-store client |

**Excluded:**

| Library | Reason |
|---|---|
| Ignite | No release in 2024 (fails rule 3) |
| Accumulo | No release in 2021 (fails rule 3) |
| Cassandra Java driver | DataStax-governed until a 2023 donation to the ASF, with a coordinate change (fails rule 2) |
| MongoDB and Redis drivers | Vendor-governed; the vendors relicensed their servers in 2018 and 2024 (fails rule 2) |
| Kafka clients | Messaging, a different function (fails rule 1). Robustness only |

## Unit and risk set

**Unit, windows and activity:** identical to the Elasticsearch risk set (Step 8).

- Event: 2021-01-14.
- Pre-event window: 2019-01-14 to 2021-01-13.
- Main horizon: 2024-11-11. Reversal window: 2024-11-12 to 2025-09-30.

**Comparison risk set:** projects whose latest pre-event release of at least one artifact declares a comparison library, non-test and non-optional.

- Projects that also declare an Elasticsearch or OpenSearch artifact at that point are excluded from the comparison group and reported separately.
- Projects in the Elasticsearch risk set are also excluded.

**Tracked line:**

- **Elasticsearch group:** the highest declared version across restricted Elasticsearch artifacts.
- **Comparison group:** priority SolrJ > Lucene core > HBase client, fixed from the last pre-event releases.

**Versions:** resolved with the Step 8 procedure: literal, own properties, own dependencyManagement, then the parent chain and BOM imports.

## Outcome measures

These are identical to Step 6 and computed the same way for both groups.

| Measure | Unit | Definition | Status |
|---|---|---|---|
| M1, upgrade hazard | Project-quarter with at least one release declaring the tracked line | 1 if any release raises the declared version of the tracked line relative to the previous release of the same artifact | Primary |
| M2, freshness | Same | 1 if the latest release declares a supplier version published within the previous 365 days | Reported only |
| M3, latest line | Same | 1 if the declared minor line, within the dependent's major version, equals the newest minor line released at least 90 days earlier | Secondary |

**Elasticsearch-only decomposition:** M1 is split into (a) raises that stay at or below 7.10.2 and (b) raises into restricted versions. This also settles the Akka decomposition debt in form.

**Periods:**

- Pre-period: 2019Q1 to 2020Q4 (eight quarters).
- Event quarter: 2021Q1.
- Post-period: 2021Q1 to 2024Q3.
- Reversal window: 2024Q4 to 2025Q3. Descriptive only.

## Diagnostics

1. **Quarterly means by group.**
2. **Equal pre-event trends:** group × quarter interactions, joint Wald test with owner-clustered SEs. Pass if p > 0.10. A linear-trend difference is also reported.
3. **Standardized differences, after propensity reweighting with trimming to 0.05-0.95.** Pass if |d| ≤ 0.25. The covariates are:
   - releases per year before the event;
   - number of artifacts;
   - project age;
   - BOM-managed supplier version before the event (the version comes from parent dependencyManagement, for example the Spring Boot BOM, which manages Elasticsearch, SolrJ and Lucene versions).
4. **Strata and exclusions (from Step 8):**
   - plugin or server-jar users vs client users (comparison analogue: Lucene vs SolrJ/HBase);
   - with and without CodeLibs;
   - BOM-managed vs directly pinned.
