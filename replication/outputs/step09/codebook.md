# Step 9 hand-coding codebook (Elasticsearch)

These rules are applied to the build files. They adapt the Step 5 codebook (`outputs/step05/codebook.md`). The coder sees build-file excerpts and branch names, not the registry outcome.

## Reference point

- **Reference commit:** the last commit on the default branch on or before the project's last release on or before **2024-11-11**.
- **Maintained release lines:** defined as in Step 5. They are other branches whose last commit falls within 183 days before that release and whose name looks like a release line.

## Coding procedure

1. **Declared dependencies.** List the Elasticsearch (`org.elasticsearch*`, `co.elastic.clients`) and OpenSearch (`org.opensearch*`) artifacts declared as library dependencies.
   - These count: Maven `<dependency>` (not `dependencyManagement` alone), Gradle `implementation`/`api`/`compile`, sbt `libraryDependencies`, and the version variables or properties that feed them.
   - Excluded: test scope, `optional`/`provided`, plugins, and benchmark or example modules.
2. **Artifact class.**
   - **Restricted:** the server jar, the high-level REST client, transport, x-pack-transport, x-content, `org.elasticsearch.plugin:*-client` and other `org.elasticsearch` artifacts.
   - **Vendor-open:** the low-level REST client (`elasticsearch-rest-client`, `-sniffer`), `co.elastic.clients:*`, and ES-Hadoop/Spark.
   - **Ignored:** never-relicensed utilities such as jna, securesm and securemock, and third-party forks under the group.
3. **Version of restricted artifacts.** Read it from the literal, a property in the repository, or the declared parent/BOM version where the managed version can be determined. Then code it as:
   - **open:** 7.10.2 or earlier;
   - **restricted:** 7.11 to 8.15;
   - **agpl:** 8.16 or later;
   - **unseen:** the version comes from an external BOM, such as `spring-boot-dependencies`, that is not in the repository. Record the BOM and its version; the coder may resolve it from known BOM contents.
4. **Shading.** Record shaded = yes when Elasticsearch or OpenSearch classes are bundled or relocated into a published artifact.
5. **Outcome code.**

| Code | Rule |
|---|---|
| `switch` | OpenSearch declared on the default branch; no Elasticsearch artifact (restricted or vendor-open) on the default branch or on a maintained release line |
| `dual` | OpenSearch and an Elasticsearch artifact both present: in separate modules, by profile or cross-build, or with one on a maintained release line |
| `upgrade` | A restricted artifact at a restricted version (7.11-8.15), and no OpenSearch |
| `upgrade_agpl` | A restricted artifact at 8.16 or later, and no OpenSearch |
| `freeze` | Restricted artifacts only at open versions (≤7.10.2), and no OpenSearch |
| `vendor_open` | Only vendor-open artifacts, and no OpenSearch |
| `removed` | None of the above declared, and no shading |
| `unclear` | Build files insufficient, or the version cannot be determined |

6. **Precedence.** When restricted and vendor-open artifacts are both present, code by the restricted artifacts.
7. **Extra fields:**
   - `kind`: `plugin` (implements an Elasticsearch plugin or depends on the server jar to run inside Elasticsearch), `client`, or `other`;
   - `bom_managed`: yes when the Elasticsearch version comes from a parent or BOM, not from the repository.

## Limits

The coder is the research assistant (an AI), as in Step 5. A human second-coder subsample remains a carried-forward debt.
