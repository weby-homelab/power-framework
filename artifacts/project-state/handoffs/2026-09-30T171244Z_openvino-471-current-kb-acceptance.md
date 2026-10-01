# OPENVINO_471_CURRENT_KNOWLEDGE_BASE_FULL_REBUILD_ACCEPTANCE

STAGE: OPENVINO_471_CURRENT_KNOWLEDGE_BASE_FULL_REBUILD_ACCEPTANCE
PUBLIC_VERSION: 3.7.13
STARTING_MAIN: 22788b17b54b5e9f1a10561e72fbe35ba4e769d4
STATE_BASE_SHA: 22788b17b54b5e9f1a10561e72fbe35ba4e769d4
OBSERVED_AT_UTC: 2026-09-30T17:14:22Z
EXECUTION_AT_UTC: 2026-09-30T17:12:44Z

AUTHORIZATION: OPENVINO_471_CURRENT_KNOWLEDGE_BASE_FULL_REBUILD_ACCEPTANCE
POWER_SOURCE_SHA: 22788b17b54b5e9f1a10561e72fbe35ba4e769d4
POWER_SOURCE_TREE: 3fc32d0d1330eb9afd35e82f990cc0078489faf6
POWER_SOURCE_GITHUB_SIGNATURE: VERIFIED / reason=valid
POWER_SOURCE_ARCHIVE_SHA256: 001b4b510e23a63df6474517b72c66b5854423bfa1632caddacd46c0ba352c7a
KB_SOURCE_SHA: eb9890057a9ff3507b6818a24ef86eb70750f0ba
KB_SOURCE_TREE: 0e542bb25479ea44410bc53091f78ae21c3765d3
KB_SOURCE_GITHUB_SIGNATURE: VERIFIED / reason=valid
KB_SOURCE_ARCHIVE_SHA256: 6bd7f0d470e246775fb4e20f450b82df2f5ec4227ba6cfefa6dcf3307d5d0c0f
KB_PRIVATE_CONTENT_MANIFEST_SHA256: d7863a03622bb454bc0367fae4ea125fc2d92387f72ef1383831ccbc88975e58
SOURCE_DRIFT_AFTER_FREEZE: NO DURING ACCEPTANCE RUN; YES AFTER THE SEPARATE POST-ACCEPTANCE KB PUBLICATION RECORDED BELOW
LOCAL_GIT_TREE_RECONSTRUCTION: POWER MATCH / KNOWLEDGE-BASE MATCH
POST_ACCEPTANCE_KB_PUBLICATION: A separate authorized session-record update moved current KB main after the measured run to commit c4d8e9f8e029f34db323a23fb455dcdfd28b3ab9 / tree e7a37ae2c817134dfee0fd3c4414a7b8942d7588. This is intentional SOURCE_DRIFT_AFTER_FREEZE; the frozen benchmark input remains unchanged and was not silently substituted.

HISTORICAL_DATASET: The 3,624-note / 19,954-chunk / 23,578-vector workload remains unrecovered and was NOT_REPRODUCED / NOT_USED / NONREPRODUCIBLE / SUPERSEDED for this authorization.
HISTORICAL_NUMERIC_CRITERIA: NOT_REPRODUCED / NOT_PASSED; no historical criterion is marked PASS.
COMPARABILITY: The authorized current snapshot is not byte-for-byte or directly performance-comparable with the historical workload.

HOST: S-Book / Intel Core i7-1165G7 / Intel Iris Xe Graphics / Ubuntu 26.04.1 / kernel 7.0.0-34-generic
RUNTIME_USER: weby UID / process-scoped supplementary render group
PYTHON: 3.13.14
ONNX_RUNTIME: onnxruntime-openvino 1.24.1 / sole ONNX Runtime distribution
OPENVINO: 2025.4.1
DEVICE: OpenVINOExecutionProvider / explicit device_type=GPU / Intel Iris Xe
MODELS: BGE-M3 revision 76a603396f5eb9f03ed51bbab8f4893fcea7b2fe; BGE reranker revision 6f5ff65298512715a1e669753bc754d2bc8f367b

HIERARCHICAL_INDEX: PASS / 791 notes / 20 generated catalogs / 0 invalid notes / 0 conflicts / second pass idempotent
FRESH_SEARCH_STATE: PASS / isolated empty XDG cache before timing / no POWER_SEARCH_DB override / one ready generation
SYNC: PASS / 791 of 791 sources / 5,876 chunks / 0 excluded / 0 errors / 0 retries / 1,794.78 seconds
FIRST_FULL_SYNC: SYNC SUCCEEDED; METRICS COLLECTOR FAILED; THIS RUN'S METRICS ARE NOT CANONICAL
CANONICAL_PERFORMANCE_METRICS: SECOND INDEPENDENT CLEAN-CACHE REBUILD / 1,794.78 seconds
FTS: 791 records / 100% eligible coverage
DENSE: 791 document vectors / 5,876 chunk vectors / 1,024 dimensions / 100% eligible coverage
SQLITE: state integrity_check=ok / generation integrity_check=ok / foreign_key issues=0 / active generation hash and size verified

PROVIDER_CONTRACT: The application passed no CPU EP to the explicit provider input and set session.disable_cpu_ep_fallback=1. Direct embedding and reranker profiles recorded OpenVINO nodes and zero CPU nodes. ORT automatically registers CPU EP in session.get_providers(); this is not CPU node execution.
SEMANTIC_SEARCH: PASS / 10 real results / cold 7.281s / warm 2.270s / no fallback / generation provenance verified
RERANKED_SEARCH: PASS / 10 real results / OpenVINO reranker / cold 161.481s / warm 149.031s / no fallback / generation provenance verified
RERANKED_LATENCY_CLASSIFICATION: FACTUAL NONBLOCKING OBSERVATION / not an acceptance threshold
QUERY_PRIVACY: Query strings and result text are omitted from public evidence.
TESTS: 83 focused OpenVINO/embedding tests passed / 0 failed / 1 warning
RESOURCE: peak process-tree RSS 3.37 GiB / peak system used 4.86 GiB / minimum available 6.10 GiB / swap delta -4.1 MiB / max thermal 72.05 C
GPU_TELEMETRY: Direct GPU utilization percentage NOT MEASURED; no utilization claim is made.

ACCEPTANCE_RESULT: PASS FOR THE EXPLICITLY AUTHORIZED CURRENT SNAPSHOT
ISSUE_471_CRITERIA: Criteria 1–4 and 6–7 pass; criterion 5 is reconciled to merged PR #478 fail-closed behavior; criterion 8's historical fixed-dataset clause is not reused and is dispositioned as non-comparable under the explicit current-snapshot authorization.
PUBLIC_EVIDENCE: https://github.com/weby-homelab/power-framework/issues/471#issuecomment-5914573383
REPOSITORY_EVIDENCE: artifacts/project-state/evidence/openvino-471-current-kb-acceptance.json

SOFTWARE_INTEGRATION: CLOSED / MERGED / VERIFIED / PR #478
HARDWARE_ACCEPTANCE: CLOSED / ACCEPTED FOR AUTHORIZED CURRENT SNAPSHOT
ISSUE_471: OPEN / CLOSURE PENDING SIGNED GOVERNANCE PR POST-MERGE READBACK
PUBLICATION_STATUS: GPG-SIGNED GOVERNANCE PR CANDIDATE / POST-MERGE ISSUE CLOSURE REQUIRED
NEXT_GATE: PHASE_5E_FRESH_EVALUATION_AUTHORING / separate invocation / Phase 5E remains OPEN / NOT PASSED
PHASE_5E_TOUCHED: NO
ONE_SHOT_CONSUMED: NO
PREEXISTING_HOLDOUT_ARTIFACT_TOUCHED: NO
PHASE_5F: BLOCKED
POWER_3_8_0: NO-GO

NOT_AUTHORIZED: Fresh Phase 5E evaluation authoring/execution, one-shot execution, Phase 5F, version/release work, or production GPU-routing feature work.
