# Step 6 comparison rule

Fixed on November 8, 2026, before any comparison-library data was extracted.

## Which suppliers count as comparison libraries

A supplier library is a comparison library if it meets all of the following:

1. **Same function, same users.** It serves an overlapping function for the same Scala developer population: a concurrency or effect runtime, streaming, or HTTP.
2. **Stable licence and governance.** It kept an OSI permissive licence and the same governance from September 2020 to September 2025, with no announced relicensing.
3. **Actively released.** It had at least one release in each year of the window.
4. **Not built on Akka.**
5. **Common support.** It has at least 50 direct dependent projects in the pre-event window. This is checked after extraction. A library that fails is dropped. The rule concerns support, not outcomes.

**Candidates meeting rules 1-4:**

| Library | Licence | Notes |
|---|---|---|
| cats-effect (`org.typelevel:cats-effect*`) | Apache-2.0 | Typelevel |
| fs2 (`co.fs2:fs2-*`) | MIT | Typelevel |
| http4s (`org.http4s:http4s-*`) | Apache-2.0 | |
| ZIO (`dev.zio:zio`, `zio-streams`) | Apache-2.0 | Ziverge and community |

**Excluded:**

- **Play:** built on Akka, so it is treated, not a comparison.
- **Monix:** releases stopped in 2022 (fails rule 3).
- **Java libraries** such as Vert.x and Netty: a different developer population (fails rule 1). They may be used in robustness checks only.

## Unit and risk set

**Unit, windows and activity:** identical to the Akka risk set (Step 4).

**Comparison risk set:** projects whose latest pre-event release (2020-09-07 to 2022-09-06) of at least one artifact declares a comparison library, non-test and non-optional. Projects that also declare Akka at that point are excluded from the comparison group and reported separately.

## Outcome measures for the pre-trend and E3 diagnostics

These are fixed now and computed identically for both groups.

| Measure | Unit | Definition |
|---|---|---|
| M1, upgrade hazard | Project-quarter with at least one release | 1 if any release raises the declared supplier version relative to the previous release of the same artifact |
| M2, freshness | Project-quarter with at least one release | 1 if the latest release declares a supplier version published within the previous 365 days |
| M3, latest line | Project-quarter with at least one release | 1 if the declared minor line, within the dependent's major version, equals the newest minor line released at least 90 days earlier |

**Pre-period:** 2020Q4 to 2022Q2.

**Diagnostics:**

1. Quarterly means by group.
2. A test of equal pre-event trends: group × quarter interactions, joint test. Pass if p > 0.10, per the Step 1 staggered-trend standard.
3. Standardized differences in project characteristics. Pass if |d| ≤ 0.25 after reweighting. The characteristics are:
   - releases per year before the event;
   - number of artifacts;
   - Scala 3 artifacts before the event;
   - GitHub owner type, where available;
   - project age.
