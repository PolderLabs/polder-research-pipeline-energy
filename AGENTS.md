---
type: guide
status: current
topic: agent-protocols
tags:
  - knowledge-base
---

# Agents

**Repository:** Polder Research Pipeline — a source-backed research and knowledge-maintenance system. It supports continuous intelligence and protocol-first systematic evidence review; those modes have different coverage and completion claims.

## Energy customer work in this fork

For energy projects, first read `docs/energy/ENERGY_WORKBENCH_PLAN.md` and
`agents/energy-engineering-agent.md`. Use `docs/energy/AGENT_DRAWING_WORKFLOW.md`
for agent-assisted concept drawing requests, `docs/energy/SITE_SURVEY.md` for intake
and `docs/energy/CALCULATION_CONTRACT.md` for the exact scope of `polder-energy`.
The energy CLI currently produces concept-only calculations and functional drawings;
bounded typed local `site_facts`, canonical schema validation and linked evidence
record hashing are implemented. Broader evidence lifecycle and dashboard integration
remain planned; local provenance checks do not establish fact truth or approval.

**Customer privacy overrides the public-vault raw-drop workflow below:** keep bills,
photographs, telemetry, addresses, meter/serial identifiers and contracts in a
private local workspace, never `knowledge-base/90-inbox/raw/` in this public repo.
Only code, reusable templates, reviewed anonymised knowledge and explicitly synthetic
fixtures belong in Git. `.research/` being ignored is not access control or encryption.
Do not expose the unauthenticated local dashboard as a customer portal.

Unknown values remain unknown. Do not equate a branch breaker to a utility fuse,
two PV labels to two verified inverters, or phase-summed energy savings to physical
per-phase fuse relief. No agent or successful unit test grants installation approval.
Run `pytest -q tests/test_energy.py` plus the existing repository checks after changes;
regenerate `knowledge-base/AUDIT.md` with the existing script when test counts change.

## Entry point

**Dashboard:** `knowledge-base/index.md` — vault stats, domain coverage, inbox status, health, self-evolution metrics.

## Repository structure

| Folder | Purpose |
|---|---|
| `knowledge-base/00-home` | Navigation hub and operating guides. |
| `knowledge-base/01-project` | Goals, requirements, ethics, stable constraints. |
| `knowledge-base/02-research` | Distilled research: models, papers, tools, technology landscape. |
| `knowledge-base/03-system` | Architecture, performance, transports, deployment, runtime. |
| `knowledge-base/04-decisions` | Decision records, comparison matrices, risk assessments. |
| `knowledge-base/05-operations` | Experiments, benchmarks, roadmaps. |
| `knowledge-base/06-sources` | Source catalog and evidence records. |
| `knowledge-base/90-inbox` | Raw drops and the intake queue. |
| `knowledge-base/99-templates` | Canonical note templates. |
| `knowledge-base/{index,AUDIT,README}.md` | Vault root durable pages (dashboard, audit, navigation). |
| `skills/obsidian-knowledgebase-curator/scripts/` | Validator and helper scripts (live at repo root, outside the vault). |

## Processing raw material

1. **Drop** — copy the raw file to `knowledge-base/90-inbox/raw/`. Keep the original filename.
2. **Register** — add a row to `knowledge-base/90-inbox/manifest.md`: `python3 skills/obsidian-knowledgebase-curator/scripts/intake_register.py --file my-report.pdf --kind pdf --owner curator`
3. **Process** — create a processing note in `knowledge-base/90-inbox/processing/<name>.md` from `knowledge-base/99-templates/intake-record-template.md`.
4. **Distill** — extract claims, label Observed / Source-reported / Inference, cross-link to domain notes, update `knowledge-base/06-sources/reference-catalog.md`.
5. **Close** — record the destination note in the manifest, mark `filed`. Move the processing note to `knowledge-base/90-inbox/archive/filed/`. The raw original stays in `knowledge-base/90-inbox/raw/`.

Full contract: `skills/obsidian-knowledgebase-curator/SKILL.md`.

For a systematic evidence review, use the protocol-first lifecycle in `knowledge-base/00-home/research-methods.md` before running any search. Freeze the protocol before activating the run; record exact searches and saved exports, candidates and duplicates, independent human screening/extraction, adjudication, appraisal, and the generated audit report. The manual intake lifecycle above handles individual artifacts and does not establish systematic coverage.

## Validators

Run from the repo root:
- `vault_audit.py` — full vault integrity: links, frontmatter, orphans, tags, structure. Exit 0 = clean.
- `frontmatter_fix.py --apply` — auto-fix missing `type`/`status`/`tags`.
- `intake_register.py --file …` — register raw item before processing.
- `new_note.py --domain 02-research --title "My Topic" --tags ai` — scaffold a note.

## Bootstrap (fresh clone)

Authoritative records under `.research/{events,tasks,runs,handoffs,protocols,searches,candidates,screenings,extractions,appraisals,classifications,sources,segments,claims,entities,gaps,conflicts,edges}/*.json` are local-only and gitignored (see `knowledge-base/AUDIT.md`, persistence boundary). Search exports and review reports are also local. On a fresh clone these records and `.research/state.json` may not exist. The correct startup sequence is:

1. Locate and validate the authoritative state backend (`polder_research.workflow._read_records(repository_root)`).
2. Build a derived snapshot if missing or stale:

   ```python
   from polder_research.maintenance import build_state

   state = build_state(repository_root=".")
   # state["work"], state["tasks"], state["runs"], state["handoffs"], state["events"], state["method_records"], state["classifications"]
   ```

   `polder_research.maintenance.build_state` is the canonical bootstrap entry point. It re-exports `polder_research.workflow.build_state`, which derives the snapshot from authoritative records without mutating them or needing a pre-existing `.research/state.json`. The snapshot exposes task/run/handoff counts, classification and method-record counts, work buckets, running and done run IDs, pending handoff IDs, and a `malformed` bucket for records that fail schema validation or JSON parsing. `.research/reports/` contains generated systematic-review audit reports; it is not part of the state bootstrap.

3. Inspect the resulting snapshot; do not assume `.research/state.json` exists before calling `build_state`.

Derived snapshots under `.research/generated/{state,health}.json` are regenerated by `python3 scripts/generate_derived.py` and remain untracked (gitignored); CI's schema-validate job regenerates them twice and checks that the outputs are byte-for-byte deterministic.

## Frontmatter schema

Every vault `.md` note needs:
```yaml
type: <value>   # index | moc | guide | template | inbox | project | research | system | decision | operation | experiment | source
status: <value>  # current | draft | stale | superseded
tags:
  - <tag>       # kebab-case, lowercase
```

## Wikilinks

Vault-root-relative from inside the vault (``knowledge-base/`` in this repo, since
AGENTS.md/CLAUDE.md live outside the vault at the repo root): `[[knowledge-base/02-research/streaming-models]]`. With alias: `[[knowledge-base/02-research/streaming-models|Streaming Models]]`.

## Related

- [[CLAUDE|CLAUDE.md]] — simplified protocol for Claude sessions.
- [[knowledge-base/00-home/vault-standards|Vault standards]].
- [[knowledge-base/index|dashboard]].
