# POWER Application API v2 — 3.7.8 Release

## Envelope

Every supported `ApplicationService` operation returns the JSON-compatible
`power.application.v2` envelope:

| Field | Contract |
|---|---|
| `schema_version` | `power.application.v2` |
| `operation` | Canonical use-case name |
| `status` | `ok` or explicit `unavailable` |
| `data` | Strictly serializable operation DTO |
| `receipt` | Content-free digest, operation, request/idempotency identifiers, timing |
| `request_id` | Safe correlation token stable for the operation |
| `actual_capability` | Executed mode, including degraded read fallback |
| `source_revision` | Active generation source snapshot or `null`/empty when unavailable |
| `degraded_reason` | Machine-readable degradation reason when applicable |

`RequestContext` rejects empty actors, unknown authority values, unsafe request
IDs, unsafe idempotency keys, and non-positive deadlines before executing a use
case. Deadline expiry cannot return a successful envelope. Receipts never carry
note bodies, secrets, absolute paths, stack traces, or model/cache paths.

## Source read model

The authoritative source remains Markdown/Git. `power sync` builds an immutable,
rebuildable generation. The same staged SQLite generation contains the FTS data
and the source projection tables:

- `source_metadata` — path, title, category, tags, size, modification time and
  content digest;
- `source_links` — deterministic resolved links;
- `source_link_ambiguities` — unresolved targets with sorted candidates;
- `source_projection_meta` — schema, source revision and row counts.

With a verified active generation, `source.list`, `source.stats`, and
`source.graph` read metadata and links from the projection and do not parse
Markdown. They perform a bounded filesystem metadata freshness check against
the projected source set; a missing generation uses an explicit bounded
degraded scan and never creates vault identity or cache state. A corrupt active
generation fails closed.

Search reads follow the same no-hidden-write rule for vault-owned state: FTS and
TF-vector requests use a verified generation when present, or a bounded
in-memory fallback when no generation exists. They do not create `.power`, a
cache namespace, or a legacy index during a normal request. The explicit
`POWER_SEARCH_DB` test/developer override retains its compatibility bootstrap
behavior and is not a production deployment profile. The bounded fallback is
labelled `no_active_generation_bounded_scan` in result metadata.

`source.read` reads one bounded file directly. Stem lookup consults the
projection; multiple candidates produce a typed conflict rather than silently
selecting the first file. `last_indexed_at` is the generation completion time,
`healthy` means verified projection coverage/integrity, and `total_links` counts
resolved links only. Ambiguities remain separately visible in graph data.

Graph `focus_path` and `max_depth` implement deterministic bounded BFS. A missing
focus path is a typed not-found result; `max_depth` is not an echoed decorative
parameter.

Projection-backed aggregate reads validate the current Markdown file inventory
against projected size/mtime metadata. A changed or missing source is reported
as typed `source_projection_stale` and fails closed; operators must run
`power sync` rather than receive stale healthy metadata.

## Transport support matrix

| Operation | Direct API | CLI | MCP stdio | Web UI |
|---|---:|---:|---:|---:|
| `source.list` | supported | not published | not published | supported through `PowerClient` |
| `source.stats` | supported | not published | not published | supported through `PowerClient` |
| `source.read` | supported | not published | not published | supported through `PowerClient` |
| `source.graph` | supported | not published | not published | supported through `PowerClient` |
| `retrieve` | supported | supported | supported | supported through `PowerClient` |
| Task/Decision/Proposal/Receipt | supported | supported adapter paths | supported adapter paths | supported through `PowerClient` |

Unused speculative source CLI/MCP commands are intentionally not frozen in this
candidate. New transport operations require explicit capability negotiation.

## Compatibility

The public immutable baseline is superseded by the unified POWER `v3.7.8`
release only when its exact commit, wheel, Web image digest, SBOM and release
receipts are read back from the publication workflow.
