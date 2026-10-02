# Implementation roadmap and acceptance criteria

The objective is a short path to useful, reviewable customer work, not an oversized
platform. Do not label planned features as implemented in proposals or demos.

## E0 - Concept-only vertical slice: implemented in this change

`init`, synthetic demos, strict input validation, simple AC replay, explicit
per-phase flows, Markdown/JSON results, Mermaid/SVG topology and hashed manifests.
Tests cover hand calculations, conservation, SOC/power limits, phase compensation,
bad input/timestamps, local-path safety and deterministic bundles.

Not delivered: production release process, final electrical calculations, customer
portal, full-year financial model, validated equipment catalogue or live controls.

## E1 - Canonical site/evidence integration: next

Reuse the existing schema registry, atomic/locking infrastructure, source records
and workflow tasks. Introduce site/fact/equipment/measurement/scenario/review schemas
with migrations. Replace v0's reference strings with resolvable source/segment IDs
and scoped, immutable evidence snapshots. Add the energy section to the existing
local dashboard; do not introduce a second frontend/backend stack.

Acceptance: an unknown main fuse or ambiguous meter boundary cannot become a
verified fact; a changed source invalidates dependent scenarios/reviews; a fresh
customer starts with no inherited values; the UI and CLI call the same validation.
Use a real site only after owner consent and local data safeguards are established.

## E2 - Measurement adapters and quality report

Implement explicit adapters for the actual customer smart-meter/P1 and PV exports.
Normalise interval kWh, cumulative registers and average kW correctly. Preserve
source files, timezone/offsets, missing data and register-reset flags. Add PVGIS as
an optional modelled-data adapter with pinned API/dataset provenance.

Acceptance: totals reconcile over matching periods; missing PV production is not
silently equated to export; no cross-meter aggregation; DST/reset/gap fixtures;
no phase split is invented from a total-only meter. Raw exports and derived data
stay private. A coarse dataset cannot certify short-duration peak behaviour.

## E3 - Scenario comparison and economics

Compare no battery, scheduling, phase redistribution, manufactured storage and DIY
options. Sweep capacity/power with equal SOC boundary treatment. Add explicit tariff
periods, tax/VAT mode, import/export charges and band thresholds; then degradation,
replacement, maintenance and financing sensitivity. Add an independent numerical
reference for the implemented dispatch model before more elaborate optimisation.

Acceptance: a hand-worked bill fixture matches; no duplicate arbitrage/self-use
benefit; initial/final energy disclosed; no annualisation from a partial year unless
explicitly labelled modelled; negative prices and zero-value storage work correctly.
Connection tariff savings stay separate and require a reviewed feasibility case.

## E4 - Equipment capabilities and typed electrical graph

Version component records by exact model/firmware. Include voltage/current/temperature
limits, BMS communication plus physical shutdown, supported island/PV modes, ratings
and evidence. Model AC, DC, PE and data ports explicitly. Tie drawings and BOM lines
to stable IDs instead of hand-maintaining independent documents.

Acceptance: incompatible voltage/port/phase combinations rejected; manufacturer
limits traceable; T1/T2/T3 rendered from the same graph used for calculations;
all diagram/schedule revisions invalidate when an affected component changes.
A commercial three-phase inverter is not assumed to accept a 48 V DIY bank.

## E5 - Electrical design checks and reviewed drawings

Implement only licensed/source-backed methods with technical review. Assess feeders,
voltage drop/rise, conductor thermal limits, board/RCD/busbar source contributions,
fault duty/disconnection and normal/island protection. Add native editable schematic
exports or a controlled QElectroTech workflow. Include structural and environmental
assessment rather than pretending an electrical graph validates the cabin.

Acceptance: calculations independently checked; applicability/uncertainty recorded;
unknown parameters block release; no generic cable table or automatic RCD rule;
phase-summed savings never masquerade as physical current relief. Surge and fault
behaviour use appropriate data, not quarter-hour active-power averages.

## E6 - Controlled review, release and commissioning

Introduce explicit lifecycle states: intake -> concept -> design-review ->
released-for-installation -> commissioned/as-built. Only authorised human reviewers
can approve a scoped revision; identities and authority must be established outside
the current unauthenticated dashboard. Software tests and typed reviewer names are
not proof of independence or professional approval.

Acceptance: immutable revision manifest, evidence and limitations, approvals,
site-specific administrative/insurance confirmations, installation method, test
plan, instrument IDs, results and as-built deviations. A changed input revokes the
applicable release. Review/override events are auditable and never agent-only.

## E7 - Laboratory replay and field-performance verification

Build a bench-first, read-only telemetry adapter and fault-replay harness. Compare
predicted versus measured energy, standby/thermal consumption and SOC. Exercise
meter loss, BMS loss, cold/full battery, module disconnect, PV loss and grid outage
within a reviewed laboratory plan. Live control needs a separate threat/safety review.

Acceptance: fail-safe behaviour is demonstrated, not narrated; evidence captured;
customer systems are not test beds for autonomous agent changes; firmware/settings
versions retained; post-installation deviations feed reviewed regression fixtures.

## Suggested team split

One owner leads site intake, source appraisal and customer deliverables; another
owns typed models, tests and automation. A suitably experienced electrical reviewer
checks electrical design/commissioning within an agreed scope. Do not treat general
software experience as proof of competence for every battery or mains task.

First practical milestone: complete one customer's survey, close its critical
unknowns, compare two or three concepts and have the assumptions independently
challenged before procuring high-energy equipment.
