---
type: guide
status: current
tags:
  - audit
  - implementation
  - research-pipeline
---

# Polder Research Pipeline — Integration Audit Snapshot

Audit date: 2026-09-22  
Implementation revision inspected: a309f7d8db443fa423fa12ca69bfdeb738984840  
Scope: eight-pass audit after the latest implementation round.

> **Historical snapshot:** the findings below describe the repository as inspected on 2026-09-22 and are not a statement of current status. A protocol-first systematic-review layer was implemented on 2026-09-24; see [[00-home/research-methods|Research methods]]. That layer adds local-only `protocols`, `searches`, `candidates`, `screenings`, `extractions`, `appraisals`, and generated `reports`. The findings remain historical; see the fresh verification note in §30 before treating any item as current.

This file intentionally contains only findings introduced or exposed by the latest implementation round.

It does not repeat the original scaffold audit, already-known dashboard redesign work, fixed historical findings, the full target architecture, or previous audit narration.

The repository has moved from a scaffold into an integration-hardening phase. The important problems are now disagreements between implemented components rather than absence of components.

## Persistence mode (resolved)

Authoritative records (`.research/{events,tasks,runs,handoffs,protocols,searches,candidates,screenings,extractions,appraisals,sources,segments,claims,entities,gaps,conflicts,edges}/*.json`) remain **gitignored** under the local mode chosen for this audit round. Search-result exports are also local inputs; `.research/reports/*.json` contains derived audit indexes. The `.gitignore` flip that would track records is a one-way door: it commits the repository's runtime state to `origin/main` and is irreversible without rewriting history. Per advisory, the flip is deferred until a follow-up ships a recorded sample plus explicit collaborator sign-off.

What is enforced *now*: every authoritative record is persisted via `polder_research.atomic.write_atomic(...)` with schema validation against the canonical schemas. Records are atomic (temp file → fsync → atomic rename) and validated against `schemas/*.schema.json` *before* they touch disk.

What remains gitignored: `.research/state.json`, `.research/health.json`, `.research/maintenance/*.json`, `.research/locks/*.json`, and `.research/generated/*` — all derived or ephemeral state, regenerable from the authoritative records.

Collaborators that need shared durable state should supply a state seed through `polder_research.maintenance.load_state(repository_root)` (see AUDIT.md §3 for the API surface); the repository remains the source of *schemas*, *templates*, *agent manifests*, and *code*, not the live record log.


| Pass | Scope | Key result |
|---|---|---|
| 1 | Implementation completeness and prior audit claims | Substantial implementation progress, but readiness/completion claims exceed the current integration state. |
| 2 | Schemas, IDs, state, and authority boundaries | Found runtime/schema incompatibilities, authoritative-state persistence ambiguity, and contract drift. |
| 3 | Agent roles, manifests, handoffs, and permissions | Role definitions exist, but runtime enforcement and several read/write/tool contracts do not yet align. |
| 4 | Source, intake, evidence, claim, and test pipeline | Found writer/schema mismatches, incomplete referential integrity, dual evidence authority, and uncollected tests. |
| 5 | Maintenance, CI, packaging, dependencies, and automation | CI is red; maintenance is partially integrated; reproducibility and generated-drift checks remain incomplete. |
| 6 | Dashboard/data-surface integration | Existing dashboard correctness debt remains and it is not yet backed by the new structured state model. |
| 7 | Security, concurrency, durability, and failure recovery | Atomicity, locking, idempotency, runtime authorization, and ingestion security need hardening before autonomy expands. |
| 8 | Documentation, repository governance, and cross-contract consistency | Readiness prose drifted from reality; source authority/startup guidance and governance still contain inconsistencies. |

The findings below are the consolidated output of these eight passes. They intentionally avoid repeating fixed historical scaffold findings or the already-documented full target architecture.

---

# 1. Current CI state is misreported

The latest inspected main revision has failing GitHub Actions jobs for:

- pytest;
- Ruff;
- vault audit;
- schema validation / generated drift;
- Gitleaks.

Dependabot configuration checks succeeded.

README/audit status text currently implies a validated foundation, so the documentation does not match the actual integration state.

Required:

- restore green CI;
- base readiness claims on the latest integration result;
- do not treat local test results or commit-message claims as equivalent to the GitHub integration result.

The connector confirmed job failures but did not expose usable failure logs during this audit.

Severity: critical.

---

# 2. Python runtime metadata conflicts with the code (historical; resolved 2026-09-24)

At the time of this audit, pyproject.toml declared Python >=3.11 and CI used Python 3.12.

Core modules call uuid.uuid7() directly.

Standard-library uuid.uuid7() is a Python 3.14 addition. The current package metadata, installer, and runtime CI now require Python 3.14 or newer; CI also compiles the source with Python 3.13 to prevent syntax-only incompatibilities.

Required:

- either keep 3.11–3.13 support using a compatible UUIDv7 implementation;
- or raise the minimum runtime to Python 3.14;
- test the declared runtime range in CI.

Severity: critical.

---

# 3. Authoritative research records are ignored as if they were derived

The implementation treats events, tasks, runs, handoffs, sources, segments, claims, entities, gaps, conflicts, and evidence edges as authoritative.

Current .gitignore ignores those JSON records and labels the runtime control-plane state derived/rebuildable.

That is incorrect for authoritative records.

Derived/rebuildable examples:

- state.json;
- health.json;
- generated indexes;
- caches;
- locks.

Non-rebuildable examples:

- events;
- tasks;
- claims;
- sources;
- evidence edges.

Required: define one durable persistence model.

Repository-backed mode:
- track authoritative records in Git;
- ignore only derived and ephemeral records.

External-state mode:
- store authoritative records in a configured durable external backend;
- keep projections/pointers in the repository.

Do not leave authoritative state as ignored local-only data.

Severity: critical.

---

# 4. Several writers generate records that violate their schemas

This is the highest-priority implementation defect.

## Segment writer

register_segment() writes created_at.

segment.schema.json forbids unknown properties and does not define created_at.

Result: a segment can be invalid immediately after creation.

## Task lease

acquire_lease() writes lease.id.

task.schema.json defines fields such as lease_token, leased_at, expires_at, and leaser, but not id.

Result: leasing a valid task can make it schema-invalid.

## Gap writer

register_gap() defaults priority to moderate.

gap.schema.json allows only:

- low;
- medium;
- high;
- critical.

Result: default gap creation is invalid.

## Source writer

register_source() can persist an empty content_sha256 when neither raw bytes nor a hash are supplied.

source.schema.json requires a 64-character lowercase SHA-256 value.

Required writer pipeline:

construct record
→ canonical schema validation
→ semantic/reference validation
→ permission/concurrency validation
→ atomic write
→ event emission

A public writer must never produce a record that the canonical registry later classifies as malformed.

Severity: critical.

---

# 5. Validation happens after invalid state can already exist

State and maintenance readers can detect malformed records, but writers do not consistently prevent malformed records from being persisted.

Required:

- validate before persistence;
- add writer round-trip tests for event, task, run, handoff, source, segment, claim, entity, gap, conflict, and evidence edge;
- make malformed-record detection a recovery safety net, not the normal integrity mechanism.

Severity: high.

---

# 6. Authoritative writes are not atomic

Core modules use direct Path.write_text() for mutable state.

Risks:

- interrupted writes can leave invalid JSON;
- concurrent agents can overwrite each other;
- last-writer-wins can silently discard semantic changes.

Required:

- write to a temporary file;
- validate;
- atomically replace;
- add record revision/hash;
- require expected revision for updates;
- surface semantic conflicts instead of silently overwriting.

Severity: high.

---

# 7. Task leases are metadata rather than safe locks

Current lease logic does not provide reliable mutual exclusion.

Missing:

- reject an existing unexpired lease;
- leased_at;
- lease-token verification;
- heartbeat/renewal;
- expired lease recovery;
- stale lock cleanup;
- atomic compare-and-set;
- collision protection.

Implement leases as real concurrency primitives before multi-agent execution.

Severity: high.

---

# 8. Task idempotency is promised but not enforced

agents/common.md says every task has an idempotency key.

The task schema makes it optional.

write_task() does not require or generate one.

The runtime does not detect equivalent prior tasks or suppress duplicate side effects.

Required:

- make idempotency key required or deterministically generated;
- check existing task/result identity before repeating side effects;
- add retry/idempotency tests.

Severity: high.

---

# 9. Execution provenance contains placeholders

Event records currently use placeholder values such as:

- instruction_version = 0.1.0;
- code_revision = HEAD.

Those fields appear authoritative but are not exact.

Record actual values for:

- instruction version;
- role-manifest version;
- config version/hash;
- schema-set version/hash;
- Git commit SHA;
- runtime version;
- model/provider when applicable;
- enabled toolset;
- policy version.

Severity: high.

---

# 10. Event schema and agent instructions disagree

agents/common.md requires events such as:

- tool.called;
- tool.failed.

The event schema does not allow them.

The same document describes timestamp/actor/event-type filenames, while the implementation writes evt_UUIDv7 filenames.

Required:

- choose one filename convention;
- unify event vocabulary;
- contract-test docs, schema, and writer behavior.

Severity: high.

---

# 11. Error taxonomy is not unified

The current event error categories are narrower than the runtime/reliability model needs.

Use one canonical taxonomy across schemas, retries, events, maintenance, and reporting.

Suggested categories:

- transient;
- validation;
- policy;
- permission;
- conflict;
- dependency;
- source-unavailable;
- source-malformed;
- budget;
- timeout;
- rate-limit;
- internal;
- unknown.

Severity: medium.

---

# 12. Agent permissions are not runtime-enforced

Role manifests now define tools, read scopes, write scopes, and forbidden paths.

No runtime authorization layer was found that actually enforces those rules.

Before autonomous execution, enforce:

- tool authorization;
- filesystem read/write authorization;
- network permission;
- code execution permission;
- destructive operations;
- schema/control-plane mutation rules.

Prompt instructions are not a security boundary.

Severity: high.

---

# 13. Several role manifests conflict with their role documentation

## Acquisition agent

Its documentation says it stores raw material, but the manifest lacks explicit raw-source storage write scope.

## Classification agent

It assigns evidence relations but cannot write .research/edges.

## Verification agent

It verifies exact evidence but cannot read evidence-edge records.

## Knowledge-query agent

It promises answer → claim → evidence edge → segment → source provenance but cannot read .research/edges.

## Synthesis agent

It promises full provenance but lacks complete segment/evidence-edge read scopes.

## Evolution agent

It references .research/schemas even though canonical schemas live under root schemas/.

## Orchestrator and research agent

Both are described as broad end-to-end coordinators.

Recommended boundary:

- orchestrator: run/task scheduling and control-plane coordination;
- research agent: bounded research execution.

Add automated contract tests comparing role docs, YAML manifests, tool registry, path scopes, and runtime authorization.

Severity: high.

---

# 14. Agent bootstrap semantics are incomplete

The common contract says no agent operates outside a task.

The orchestrator is responsible for creating the initial run/tasks.

Define an explicit bootstrap rule:

- human/runtime creates the initial orchestration task; or
- bootstrap/admin operations are a separate permitted control-plane operation.

Severity: medium.

---

# 15. Evidence relationships have two writable authorities

The implementation now contains both:

- standalone evidence-edge records;
- embedded claim.evidence arrays.

Both can encode source, segment, relation, confidence, directness, and locator.

That creates synchronization risk.

Recommended:

- standalone evidence edges are authoritative;
- claims reference edge IDs or expose a generated projection;
- reports derive provenance from the edge records.

Severity: high.

---

# 16. Referential integrity is incomplete

Evidence-edge registration performs endpoint validation, but other writers are weaker.

Before persistence, verify relationships such as:

- segment source exists;
- every claim source exists;
- conflict claims exist;
- conflict contains at least two distinct claims;
- entity references exist;
- task/run/handoff references resolve;
- decision-impact references resolve.

Build one reusable reference validator.

Severity: high.

---

# 17. Evidence tests contain accidentally uncollected tests

tests/test_evidence_edge.py contains several intended tests indented inside the inbox fixture after its return statement.

Those functions are not normal pytest test cases.

Affected intended coverage includes:

- segment/source ownership;
- invalid relation rejection;
- missing endpoint rejection;
- locator requirement;
- locator validation;
- persisted edge behavior.

Fix the test structure and add a sanity check that critical test names are collected.

Severity: high.

---

# 18. Source deduplication is fragile around malformed source records

find_duplicate_source() directly parses existing source JSON.

A malformed source can break duplicate lookup.

Required:

- use the canonical validated-record loader;
- isolate/report malformed records;
- continue scanning valid records;
- later normalize DOI, canonical URL, repository URL, version/tag, and commit identity.

Severity: medium.

---

# 19. Intake still duplicates canonical vocabulary

The control-plane config exists, but the intake implementation still hard-codes:

- statuses;
- kinds;
- source-type mappings.

The Markdown manifest also still uses filename as identity.

Required direction:

- consume canonical config/schema definitions;
- create one structured intake record per item;
- use stable intake ID;
- reference canonical source ID;
- generate manifest.md as a human projection.

Severity: medium.

---

# 20. New-note generation does not use the new template authority

TemplateRegistry now exists, but the new-note implementation still:

- hard-codes domain/type/status vocabulary;
- builds the body directly;
- uses ASCII-only slugging.

Required:

- resolve templates through TemplateRegistry;
- render supported placeholders;
- validate frontmatter;
- use Unicode-safe filename behavior or stable-ID-backed identity.

Severity: medium.

---

# 21. Maintenance is only partially integrated

The new maintenance evaluator is useful, but its implementation and policy are not fully aligned.

New gaps:

- code references thresholds absent from current config;
- superseded sources are used as a duplicate proxy;
- stale status is consumed without a general freshness engine deriving it;
- research-health triggers and structural passes are not cleanly separated;
- maintenance classes are not explicit;
- health output does not yet aggregate the full research-quality state.

Treat the current module as an initial deterministic evaluator rather than a completed maintenance engine.

Severity: medium.

---

# 22. Gitleaks integration (historical; resolved 2026-09-24)

At the time of this audit, the secret-scan job was red because the organization-owned repository required a Gitleaks Action license. On 2026-09-24, the latest Actions logs confirmed that cause. The workflow now installs a pinned Gitleaks CLI and scans Git history; it does not depend on the licensed action. A local scan of all 43 available commits found no leaks. The next pushed workflow run remains the authoritative CI verification.

Severity at audit time: high. Current status: configuration corrected; awaiting CI run.

---

# 23. Dependency reproducibility is incomplete

Some developer dependencies are pinned, but CI still performs floating installation steps such as pip upgrade and a broad Ruff install.

There is no full dependency lock for the runtime and CI toolchain.

Choose a deterministic strategy:

- lockfile;
- constraints file;
- fully pinned generated CI requirements.

Severity: medium.

---

# 24. Generated-drift validation is mostly a no-op

The CI job checks Git diff under .research/generated only if that directory exists.

It does not run a canonical generator first.

The directory can also be absent/ignored.

The real contract should become:

generate all tracked derived artifacts
→ git diff --exit-code

Do not claim generated-drift enforcement until that exists.

Severity: medium.

---

# 25. Source-authority guidance conflicts

.wolf/anatomy.md describes 06-sources/reference-catalog.md as canonical.

The structured source records are supposed to be authoritative.

Use one rule everywhere:

Authoritative source record store = canonical.
Markdown source catalog = human projection.

Severity: medium.

---

# 26. Startup guidance assumes state.json already exists

OpenWolf startup guidance tells agents to inspect .research/state.json.

That file is derived and may not exist on a fresh clone.

Correct startup sequence:

1. locate and validate the authoritative state backend;
2. rebuild state snapshot if missing or stale;
3. inspect the resulting snapshot.

Severity: medium.

---

# 27. Implementation status should be machine-verified

The repository now changes quickly enough that manually maintained readiness prose can become stale within one commit.

This audit found status text claiming clean validation while GitHub Actions was red.

Consider generating a small status block containing:

- implementation revision;
- CI result;
- supported Python versions;
- schema count;
- test count;
- latest successful audit/validation revision.

Human documentation should explain capabilities. Machine-derived state should report readiness.

Severity: medium.

---

# 28. Recommended implementation order

Stabilize the new implementation before adding broader autonomy.

1. Inspect and fix all failing GitHub Actions jobs.
2. Resolve Python/UUIDv7 compatibility.
3. Fix writer/schema mismatches.
4. Validate every authoritative writer before persistence.
5. Repair evidence test collection.
6. Define durable authoritative-state persistence.
7. Add atomic writes.
8. Add optimistic concurrency.
9. Implement real lease ownership, expiry, and recovery.
10. Enforce task idempotency.
11. Synchronize event schema and agent instructions.
12. Enforce role manifests at runtime.
13. Fix role permission/tool mismatches.
14. Choose one evidence-relation authority.
15. Enforce referential integrity.
16. Remove duplicated intake/note vocabularies.
17. Connect note generation to TemplateRegistry.
18. Finish maintenance/config integration.
19. Make dependencies and generated-drift checks deterministic.

Do not prioritize autonomous research workers before this stabilization batch is complete.

---

# 29. Exit criteria

This audit can be considered resolved when:

- latest main CI is green;
- declared Python versions match tested runtime behavior;
- every authoritative writer passes schema round-trip tests;
- invalid records cannot be persisted through normal APIs;
- authoritative records have a durable persistence model;
- writes are atomic;
- mutable records use concurrency protection;
- leases provide real mutual exclusion and expiry recovery;
- task idempotency is enforced;
- execution provenance records actual revisions/versions;
- role manifests are runtime-enforced;
- role docs, manifests, tools, and permissions agree;
- evidence relations have one authority;
- referential integrity is enforced;
- critical evidence tests are actually collected;
- intake and note tools consume canonical config/registries;
- maintenance implementation matches its configuration;
- secret scanning is green;
- dependency installation is reproducible;
- generated-drift validation actually regenerates and compares outputs;
- documentation does not claim a validation state contradicted by CI.

---

# 30. Evidence limitations

This audit inspected:

- the current repository tree;
- current source code;
- current schemas;
- current role manifests;
- current tests;
- current CI workflow;
- GitHub Actions job conclusions for the inspected implementation revision.

The audit above is a historical snapshot; its implementation status block is generated from repository state. On 2026-09-24, Actions logs were retrieved for commit `2b6ced9`. They confirmed failures in the moved config path, the organization-licensed Gitleaks action, and Ruff lint/format checks. The config path, Gitleaks integration, Ruff issues, formatter drift, and self-referential status field have been corrected. Local verification passes (226 tests, Ruff, vault audit, installer syntax, and a 43-commit Gitleaks history scan). The pushed workflow remains the final CI check.

On 2026-09-25, preparing a GPU (RTX 5060 Ti, WSL2) Laya environment exposed a
packaging defect and a pre-existing test-suite regression. The wheel built by
Hatch packaged `src/polder_research` only, so the canonical `schemas/*.schema.json`
data was absent from a non-editable install. `SchemaRegistry` then raised
`SchemaError: schema directory does not exist` at import time, which made every
`polder-research` subcommand unusable for anyone who installed by wheel rather
than by the documented editable install. The wheel now force-includes the
canonical schemas. `SchemaRegistry(explicit_root)` uses only that root's
`schemas/` directory; package-schema fallback is selected explicitly through
`registry_for_root(..., allow_package_fallback=True)` when a caller supports
schema-less workspaces. Empty schema directories are rejected, and partial
local registries remain authoritative.

Wheel-installed CLI commands accept a shared `--root` option before or after
the command and route workspace reads and writes to that directory. When
omitted, a source checkout uses its checkout root and a wheel install uses the
current directory. The wheel bundles the `vault_audit.py` and
`frontmatter_fix.py` scripts used by those CLI commands. Source checkouts use
their own copies during development; a target workspace is data and cannot
provide executable replacements. Workspaces still supply their knowledge base
and schemas, and vault audit validates against those workspace schemas, with
the packaged registry as an explicit fallback when schemas are absent.

At the same time 23 tests were failing on `main` before any change here. Two test
fixtures wrote inline schemas that predated the required non-empty `$id`; three
fixture roots had no `schemas/` directory, so registry resolution raised instead
of falling back; one test asserted tag mutation that `merge_proposals` no longer
performs (effective metadata is projected separately) and had no production
caller; and one Jev failure test depended on the optional `typesafe-sdk` extra
being installed. All are corrected, and `schemas/__init__.py` now reports the
failing instance path in `SchemaError` so a config error names the offending key.
One real behaviour gap was fixed rather than papered over: the persisted-failure
allowlist omitted the Jev missing-dependency message, so that entirely
diagnosable cause was recorded as a generic "classification provider or response
failed".


<!-- status:begin -->
<!--
Machine-verified implementation status. Regenerated by
`scripts/emit_implementation_status.py`. Do not edit by hand.
-->

- python: `3.14`
- schema_count: `27`
- test_count: `337`
- last_audit_revision: `a309f7d8db443fa423fa12ca69bfdeb738984840`

<!-- status:end -->
