# Step 12 text codebook: motives stated in issues and pull requests

Fixed on November 10, 2026, before any issue text from `data/raw/step12/issues/` was read.

## Unit and corpus

- **Unit:** one issue or pull request returned by the Step 12z search (title plus the first 4,000 characters of the body). Comments are not in the corpus.
- **Corpus:** treated projects' own GitHub repositories. Akka items created from 2022-06-01; Elasticsearch items from 2020-10-01.

## Step 1: relevance (R)

**R = 1** if the item discusses at least one of:

- the supplier's licence change;
- a move to, from or alongside the fork (Pekko, OpenSearch);
- the choice of supplier version in light of the relicensing (staying on 2.6 / 7.10, or taking restricted versions).

**R = 0** otherwise. Examples: the project's own LICENSE file, licence headers, other libraries' licences, Scala Steward bumps that do not mention the licence or the fork, and automated dependency updates with no text beyond the version.

Automated bots (Scala Steward, Dependabot, Renovate) are R = 1 only if their text mentions the relicensing or the fork, which they normally do not.

## Step 2: motive codes (multi-label, R = 1 only)

| Code | Meaning | Model term |
|---|---|---|
| **LEGAL_OWN** | The licence terms bind the project itself: fees, compliance, commercial use, legal review, or licence incompatibility with the project's own licence or its foundation's policy (for example ASF Category X). | e_i·c |
| **LEGAL_USERS** | Downstream users or customers cannot or will not accept the licence, or asked for the fork. | e_i·c through the user base |
| **TRUST** | Distrust of the supplier: fear of further restriction, "rug pull", vendor lock-in, preference for foundation or community governance. | h·Δπ |
| **AGEING** | Security fixes, CVEs, end of patches for the open line, bugs fixed only in newer versions. | d(t) |
| **COMPAT** | Compatibility needs: Scala 3, JDK, or another dependency requiring a newer supplier or fork version. | g(t), d(t) |
| **COORD** | Waiting for, or following, other dependencies or the ecosystem (ports not yet available, Play 3, other libraries moved). | k_i(t) |
| **COST** | Effort, risk or breakage of migrating or upgrading. | a_i, k_i |

A code is assigned only when the motive is **stated**, not inferred from the action.

## Step 3: action (R = 1 only, one value)

SWITCH (replace with the fork), DUAL (publish both), STAY (keep the open line), UPGRADE (take restricted versions), REMOVE (drop the supplier), DISCUSS (no decision in the item).

## Coders and validation

- **Coder A:** the language model in this session, reading every item under this codebook.
- **Coder B:** a keyword rule, fixed here:
  - LEGAL_OWN: licen[cs]e fee | commercial licen | BSL | business source | ELv2 | SSPL | Category X | legal | complian | incompatib
  - LEGAL_USERS: (users | customers | downstream | companies) within 80 characters of licen[cs]e | can't use | cannot use
  - TRUST: trust | rug | lock-in | lock in | vendor | governance | foundation | future (licen | change) | community-driven
  - AGEING: CVE | security | vulnerab | end of life | EOL | patch | no longer maintained | unmaintained
  - COMPAT: Scala 3 | scala3 | JDK | Java 2[1-5] | Java 17 | compatib
  - COORD: wait | depend(s|ency|encies) on | ported | port of | ecosystem | Play 3 | play 3
  - COST: effort | breaking | migration (cost | effort | path) | rewrite | too much work
- **Agreement:** Cohen's κ between A and B, per code, on the R = 1 items.
- **Human validation (open debt):** a stratified sample of 60 items (30 per event, oversampling LEGAL and TRUST) is exported for a human coder. Until it is coded, the motive shares are reported as model-coded with keyword agreement only.

## Reporting

- For each event: the number of repositories with at least one R = 1 item, and the code shares among projects (one project counts once per code).
- Cross-event contrast: the LEGAL share against the TRUST share.
  - The model predicts LEGAL to be present in Akka and nearly absent in Elasticsearch (restriction scope).
  - TRUST should be present in both.
- This is a description of stated motives in public text, which is a selected subsample: projects that discuss their choice.

## Coder A, as run (added November 11, 2026)

- **Model:** Claude Opus 5.5 (`claude-opus-5-5`), used interactively in the analysis session on November 10, 2026.
- **Instruction:** this codebook.
- **Input:** `text_for_coding.txt` and `text_for_coding_projects.txt`. These are the items selected by `step12b2_project_listing.py`: title plus the first 4,000 characters of the body.
- **Process:** the model read the items in batches and wrote repository-level codes to `text_coded_projects.csv`.
- **Not controlled:**
  - sampling settings (temperature and similar);
  - the exact prompt wrapper.

  So the codes cannot be regenerated exactly. The validation against a human coder (Step 14, section 7) is the check on them.
