# Polder Energy Engineering Workbench

Status: proposed product direction with a runnable concept-only first slice.
Owner: PolderLabs. Decision date: 2026-10-02.

## 1. What we are building

A local-first engineering workspace that turns customer questions into traceable,
reviewable energy-system options and, eventually, controlled installation packs.
Not another chatbot that recommends a battery from an annual bill.

The working loop is:

```text
Survey and original evidence
  -> verified site facts + explicit unknowns
  -> source-backed equipment capabilities and constraints
  -> candidate electrical architectures
  -> deterministic calculations and measured-data replay
  -> comparable options + concept drawings + preliminary bill of materials
  -> independent engineering review and site-specific approvals
  -> released installation pack
  -> commissioning and as-built records
  -> measured performance compared with predictions
  -> reusable, anonymised engineering knowledge
```

One validated project model must eventually generate the calculations, drawings,
component schedule and handover. A change to an inverter, phase assignment, feeder
or battery module must invalidate every affected result and approval.

The commercial unit is a **customer/site assessment and engineering dossier**.
Start with useful work on real sites, not a public multi-tenant SaaS platform.

## 2. Existing repository: preserve the useful foundation

The inspected baseline is commit `63f1e3a5252f0e5e2bc12b633e328b693f548316`.
It is the general Polder Research Pipeline, with a Python package, local `.research/`
records, evidence/provenance, research workflows, agents, a local dashboard,
JSON schemas, atomic-write helpers and CI. Its README and installer still describe
the upstream generic research application.

Extend that foundation rather than creating a second research database or a new
web framework. Keep Python for the calculation core. Keep the existing evidence
system for sources, segments, claims, conflicts and gaps. Add typed energy-domain
records and adapters incrementally. Do not make an LLM the numerical engine.

The current local dashboard has no authentication according to the existing
README. It must not be exposed as a customer portal. Separate customer folders
are organisation, not authenticated tenant isolation.

## 3. What this first change actually implements

The `polder_research.energy` module and `polder-energy` entry point provide:

- Local customer-project initialisation with an unknown scenario, not invented ratings.
- Explicitly synthetic one-phase and three-phase demonstration data.
- Strict input-field, numeric and timestamp validation.
- Canonical Draft 2020-12 validation for the existing v1 project envelope.
- Read-only exact-contract CSV preflight with UTC coverage, per-channel kWh,
  input hashes and explicit unverified source boundaries.
- AC self-consumption replay with charge/discharge limits, SOC bounds, conversion
  efficiencies, auxiliary consumption, and per-phase active-power accounting.
- Same-profile no-storage baseline comparison with signed import/export differences,
  SOC/loss/auxiliary disclosure and per-phase interval-average peaks.
- A phase-summed meter model while retaining physical power flows on every phase.
- Deterministic JSON results, Markdown report, Mermaid/SVG, editable draw.io concept
  sheet and generic functional-block QElectroTech export.
- Content hashes for inputs, engine source and generated outputs.
- Refusal to overwrite an existing project or a modified generated run.
- An unconditional `concept_only` release status.

This is not yet a full site graph, CAD application, authenticated approval system,
network protection solver, multi-option optimizer, tariff model or live
energy-management controller. Evidence references are carried as pointers; they
are not yet resolved against source records. The project envelope schema is
validated, but site/equipment facts and workflow/evidence integration remain
planned. The QElectroTech XML has structural tests but has not been opened/rendered
in the target editor. Its local file workflow is not a multi-user transaction
system.

## 4. Initial customer scope

Support three deliberately bounded project types first:

| Type | Questions we must answer |
|---|---|
| Existing PV, one-phase supply | What useful energy can be shifted? What inverter power and physical location are feasible? |
| Existing PV, three-phase supply | Is one-phase storage enough for the stated goal, or is actual per-phase support required? |
| Outdoor cabinet/cabin retrofit | Is the site suitable, what feeder is needed, and what environmental/incident controls are required? |

Later, with additional expertise: small-business machinery, deliberately islanded
microgrids, generators and marine/shore-power interfaces. Do not treat a boat as
just another house circuit: identify the vessel boundary, earthing/isolation,
corrosion and applicable marine requirements before designing that interface.

Always compare against **no battery**, load scheduling, phase redistribution and,
where appropriate, a complete manufactured battery. Do not optimise only among
battery products and miss a cheaper way to meet the customer's objective.

## 5. Operating sequence for every customer

### A. Agree the outcome

Record whether the objective is self-consumption, backup, reducing a connection,
reducing export charges, dynamic-price operation, or a combination. Rank the
objectives. Define acceptable interruptions, backup loads, autonomy, budget,
maintenance responsibilities and likely future loads. Distinguish a target of
zero export from guaranteed zero export under all conditions.

Output: signed-off requirements and a scope boundary, not a component order.

### B. Survey the actual site

Use [SITE_SURVEY.md](SITE_SURVEY.md). Identify each meter and installation
separately. Collect labels, drawings, cable routes, distances, loads and environmental
constraints. Mark observations, customer statements, inferences and verified facts
separately. A photo can show a marking; it does not establish hidden wiring.

Output: site fact register, evidence index, unknowns, and measurement plan.

### C. Measure and normalise

Collect full-year import/export and PV production where available, plus sufficiently
fast per-phase measurements for demand analysis. Keep the original files unchanged.
Record timestamp meaning, timezone, units, sensor location, interval duration,
missing periods, register resets, calibration and quality flags. Reconcile totals
against bills over matching periods. Do not mix supplies or billing years.

The first replay tool accepts **separate load and PV active-power channels per
phase**, not raw P1 exports. A P1/import-export adapter must reconstruct or explicitly
limit what can be inferred. Unknown phase distribution stays unknown. Generated
weather/PVGIS series must never be relabelled as measurements.

Output: normalised series with a quality report and reproducible conversion record.

### D. Compare architectures before brands

Evaluate no-storage baseline; one-phase AC storage; one-phase storage on a
three-phase site; true three-phase storage; and a hybrid replacement only when
its integration and costs justify it. Explicitly distinguish grid-side PV from
PV capable of operating in a designed island.

Output: topology alternatives and a documented elimination/comparison matrix.

### E. Calculate and challenge the design

Separate energy sizing from power sizing and electrical protection. Run capacity
and power sweeps, preserve SOC boundary conditions and compare measured periods
rather than pretending a sunny week represents a year. Include losses, standby,
heating/cooling and planned demand changes. A reviewer must be able to reproduce
each important figure without an LLM.

Output: versioned calculation bundle and remaining engineering questions.

### F. Prepare drawings and a procurement schedule

Generate concept diagrams from the same scenario. After the electrical graph is
implemented, generate draft single-line diagrams and schedules from stable equipment
IDs. Detailed terminal drawings, PE/N arrangements and protection settings require
an engineering tool and review; an attractive SVG is not an installation drawing.

Output: revision-linked draft drawings, component schedule and unresolved ratings.

### G. Review, release, commission

Obtain the required site-specific technical review, insurer/owner agreements and
administrative confirmations. Record named reviewers and the exact revision they
reviewed. Commission against a test plan; collect test equipment IDs, measured
results, settings backups, deviations and as-built drawings. Deliver operating,
emergency isolation and maintenance instructions.

Output: reviewed release, followed by an independently traceable as-built dossier.

## 6. Domain model and one source of truth

Introduce these versioned record types in the existing schema registry, not as
unrelated spreadsheet columns or free-form LLM state:

| Record | Essential content |
|---|---|
| Customer workspace | Pseudonymous ID, ownership, storage policy and disclosure permissions |
| Site / connection | Jurisdiction, meter boundary, verified phase count, connection details |
| Fact | Value, unit, evidence class, source/segment ID, observed date, reviewer, uncertainty |
| Measurement series | Channel semantics, interval, units, timezone, sensor, quality and input hashes |
| Equipment | Exact model/revision, electrical ports, temperature curves and sourced limitations |
| Topology | Nodes, typed ports, edges, phases, protection boundaries and operating modes |
| Scenario | Immutable site revision + equipment revisions + policy + input datasets |
| Calculation run | Model version, inputs, outputs, warnings, tests and reproducibility manifest |
| Drawing / BOM | Component IDs, source scenario, calculation dependencies and revision |
| Review | Scope, reviewer, evidence, limitations, decision and invalidation triggers |
| Commissioning | Instrument IDs, measurements, settings, deviations and as-built references |

A fact should distinguish `observed`, `customer_reported`, `source_reported`,
`inferred`, `assumed`, `verified` and `unknown`. A photograph-derived value is not
silently promoted to `verified`. Safety-critical unknowns block a construction
release. Conflicting observations create a conflict record, not an averaged value.

Equipment compatibility is a relation between exact battery/BMS/inverter/firmware
configurations. A shared CAN connector or nominal voltage is not enough.

## 7. Trust and validation architecture

Use three separate layers:

1. **Research:** source discovery, manufacturer documents, applicable standards,
   evidence extraction and conflicts. AI can propose candidate facts with provenance.
2. **Engineering:** typed inputs, deterministic numerical functions, constraints,
   graph checks and explicit approximation boundaries. AI invokes tools; it does
   not override a failed check or invent a missing rating.
3. **Release:** scoped human technical review and site verification. A passing test
   suite proves specified software behaviour, not that the physical installation is safe.

Every calculation needs a method identifier, units, assumptions, validity envelope,
source references, golden fixtures, edge cases and an independent comparison before
it can support consequential design decisions. See [CALCULATION_CONTRACT.md](CALCULATION_CONTRACT.md).

Use mutation and adversarial tests: swapped phases, missing neutral, two meter
boundaries, unknown cable, full/cold/disconnected battery, missing BMS data, inverter
trip, grid outage and communications loss. Bench/hardware tests belong in an
isolated laboratory workflow, not an agent-controlled customer installation.

## 8. Diagrams, tools and practical deliverables

Use a typed graph as the eventual common source for SLD, cable schedule, equipment
schedule, BOM and commissioning checklist. Separate AC power, DC power, protective
earth and communications. Draw normal and island modes separately. Never infer a
protective-earth arrangement from an energy-flow graph.

The first prototype now emits a deterministic draw.io concept sheet, SVG preview
and QElectroTech functional-block schematic alongside Mermaid/SVG topology. Both
editable drawings share stable component IDs and the calculation run revision, but
are not authoritative calculation inputs: manual edits do not flow back to the
model. Use local desktop editors; do not embed a hosted editor before a data-privacy
review. Keep QElectroTech as a candidate for reviewed schematics and panel layouts,
not a simulation engine. Do not build an in-house CAD editor at this stage.
Preserve native editable files, revision IDs and cross-references back to the
project model. See [TOPOLOGIES_AND_DRAWINGS.md](TOPOLOGIES_AND_DRAWINGS.md) and
[RESEARCH_SOURCES.md](RESEARCH_SOURCES.md) for the concept-only limits and tool
references.

Prioritise tools in this order: intake/data quality; replay; phase analysis;
equipment compatibility; economic comparison; graph/schedule generation; electrical
checks; field-test capture; post-installation calibration. Add a tool only when a
customer task and a testable correctness contract justify it.

## 9. Economics without misleading payback

Keep energy savings, connection-charge savings, backup value and possible trading
income separate. Model supplier import/export terms, taxes and VAT consistently,
including applicable effective dates and standing/banded charges. A network downgrade
requires more than a favourable energy replay, and may be achievable without a battery.

Do not count initial stored energy as free recurring benefit. Do not double-count
self-consumption and arbitrage. Include lost export remuneration, conversion and
auxiliary losses, degradation, maintenance, replacement, financing and residual value.
Show downside/base/upside assumptions and sensitivity rather than one precise payback.
No tariff model or annual financial claim is implemented by the first CLI.

## 10. Privacy and multiple customers

This GitHub repository is public. Commit code, templates, source links and invented
fixtures only. Keep customer bills, images, names, addresses, meter identifiers,
serial numbers, contracts and telemetry out of Git. Removing a file later does not
remove it from history. Public issue discussions and CI logs are also disclosure paths.

Use separate local workspace roots for unrelated customers where practical. `.research/`
is already ignored, but Git ignore rules are not access control, encryption or backup.
Provide encrypted storage and backups, explicit retention/deletion policies, and a
customer-scoped retrieval boundary before multi-user use. Do not expose the existing
unauthenticated dashboard. Cloud-model use requires a deliberate per-project decision.

Share anonymised lessons only after human review. No synthetic example may quietly
inherit a real customer's address, meter ID or measurements.

## 11. Source maintenance and legal applicability

Use manufacturer primary sources, official standards publishers, the grid operator,
NIPV, IPLO and competent local authorities. Record edition, section, retrieval date,
content hash and licensing restrictions. Revalidate affected claims before a design
release; an old source remaining reachable does not establish current applicability.

Do not scrape and republish licensed standards. Encode reviewed methods and citations
only within the rights held. Do not hard-code a universal battery-capacity exemption,
fire separation distance, RCD type or cable ampacity. Site use, construction, operating
mode, equipment instructions and the applicable rule set matter.

The initial source register distinguishes reviewed web documentation from sources
that still require full technical/applicability review.

## 12. What success looks like

For the next real customer, PolderLabs can produce a complete intake, an honest list
of blockers, comparable concepts and reproducible preliminary energy results without
retyping values into disconnected documents. A reviewer can trace a number or component
to its input and source. The resulting installation, when released by the appropriate
people, can be tested against the same requirements and compared with predictions.

Track survey completeness, time to a reviewable concept, unresolved critical facts,
reproducibility, prediction error and commissioning deviations. Do not measure success
by the number of generated pages, agent calls or batteries recommended.

Implementation order and acceptance criteria: [ROADMAP.md](ROADMAP.md).
