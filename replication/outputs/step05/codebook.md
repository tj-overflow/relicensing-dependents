# Step 5 hand-coding codebook

These rules are applied to the build files. The coder sees build-file excerpts, branch names and README text. The coder does not see the registry outcome.

## A. Outcome at the horizon (from the repository)

**Reference commit:** the last commit on the default branch on or before the project's last release on or before 2025-09-30.

**Maintained branches:** any other branch whose last commit before 2025-10-01 falls within 183 days before that release. Bot branches are excluded. A branch counts as a maintained **release line** only if its name looks like a release line, for example `1.x`, `release-*`, `series/*`, `akka`, `pekko`, or a version. Feature branches do not count.

**Coding procedure**

1. **Declared library dependencies.** List the Akka (`com.typesafe.akka`, `com.lightbend.akka`) and Pekko (`org.apache.pekko`) artifacts declared as library dependencies. These sources count:
   - sbt `libraryDependencies`;
   - Maven `<dependency>`;
   - Gradle `implementation`/`api`/`compile`;
   - version variables that feed them.
2. **Excluded scopes.** These do not count as a library dependency: test or `it` scope, `Optional`/`provided`, sbt plugins (`project/plugins.sbt`), and benchmark or example modules.
3. **Akka version.** Read the version from the literal or from the variable definition:
   - 2.6.x or earlier is **open**;
   - 2.7 or later is **BSL**;
   - Akka HTTP 10.2.x or earlier is open; 10.4 or later is BSL;
   - other modules follow the same rule as their release lines at the event.
4. **Shading.** Record **shaded = yes** when Akka or Pekko is bundled into a published artifact. Signs include `maven-shade-plugin` relocations of `akka`/`pekko`, sbt-assembly publishing, or a dedicated shaded module.
5. **Outcome code.**

| Code | Rule |
|---|---|
| `switch` | Pekko declared on the default branch, with no Akka on the default branch or on any maintained release line |
| `dual` | Akka and Pekko both present at the reference point: in separate modules, through a cross-build axis, or with one on a maintained release line |
| `upgrade` | Akka declared with any BSL version, and no Pekko |
| `freeze` | Only open Akka versions declared, and no Pekko |
| `removed` | Neither declared and no shading of either |
| `unclear` | Build files are insufficient, for example versions supplied by an external BOM that cannot be seen |

6. **Shaded projects.** A project whose only use is shaded Pekko is coded `switch` with shaded = yes. Only open Akka is coded `freeze` with shaded = yes, and so on.

## B. Maintainer and exposure (from the GitHub owner profile and README)

**Hand-coded maintainer type:**

| Code | Meaning |
|---|---|
| `company` | A for-profit firm maintains the project, or the project is a component of a firm's product or service. Signs: an org named after a firm, a README naming a commercial product, or an employer-branded repository |
| `foundation` | Apache, Eclipse, CNCF, Linux Foundation or similar |
| `academic` | A university or public research body |
| `individual` | A personal account, or a community org without a firm behind it |

`exposed_hand = 1` if `company`, else 0.

**Automated proxies to be validated:**

- `A1` = 1 if the GitHub owner type is Organization and the project is not foundation-hosted.
- `A2` = 1 if `A1`, or the owner is a User whose profile `company` field is non-empty.

**Kill test (Step 1, section 8):** agreement of at least 80% and Cohen's kappa of at least 0.6 between the automated proxy and `exposed_hand`.

## C. Limits

- **Coder.** The coder is the research assistant (an AI) reading extracted build files. This is a single coder. For a publishable inter-rater statistic, a second human coder should code a random subsample of at least 20 projects using this codebook.
- **Blinding.** The coder is blind to the registry outcome in the report but not fully: some outcomes were seen in Step 4 summaries, for example Flink and Gatling.
