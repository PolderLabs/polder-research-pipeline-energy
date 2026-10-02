# Calculation contract - AC concept model v0.1

Implementation: `src/polder_research/energy.py`.
This document defines what the implemented model means, not a general installation method.

## Scope

The model replays interval-average **active power** for an AC-coupled battery while
the grid is available. It uses a greedy self-consumption policy and assumes the
meter nets simultaneous active power across phases. It preserves the physical
per-phase active-power flows separately.

Supported: single-phase supply/storage, single-phase storage on one phase of a
three-phase supply, and balanced three-phase storage. The latter divides the total
battery AC command equally among phases. It is not independent per-phase regulation.
Manufacturer capabilities and metering behaviour require separate verification;
see sources S1 and S2 in [RESEARCH_SOURCES.md](RESEARCH_SOURCES.md).

Not supported: RMS-current/fuse suitability, voltage rise/drop, reactive power,
harmonics, inrush, fault interruption, protection coordination, neutral/earthing,
islanding, backup autonomy, black start, PV frequency control, temperature curves,
ageing, tariff optimisation, dynamic prices, export guarantees or construction approval.

## Project input: schema version 1

`project.json` has the following required keys and one optional additive field:

| Field | Contract |
|---|---|
| `schema_version` | Integer 1 |
| `id` | 1-64 lowercase letters/digits/hyphens; must match its directory |
| `data_class` | `customer` or `synthetic` |
| `evidence_refs` | List of reference strings; existence/relevance is not yet validated |
| `site_facts` (optional) | Typed local facts and source/optional segment links as described below |
| `assumptions` | Nonempty list of explicit assumptions |
| `unknowns` | List of unresolved work items; empty does not constitute approval |
| `scenario` | Null during intake, otherwise the complete scenario below |

Scenario fields are mandatory, with no unknown fields or implicit numeric defaults:

| Field | Unit / permitted value |
|---|---|
| `grid_phases` | Integer 1 or 3 |
| `topology` | `single_phase` or `three_phase_balanced` |
| `battery_phase` | 1-based existing phase; use 1 (unused) for balanced topology |
| `nominal_kwh` | Positive nominal battery energy in kWh |
| `minimum_soc`, `maximum_soc`, `initial_soc` | Fractions in [0,1], ordered with a nonzero operating window |
| `charge_limit_kw_ac`, `discharge_limit_kw_ac` | Nonnegative total AC power in kW; not kVA or DC ratings |
| `charge_efficiency`, `discharge_efficiency` | Each in (0,1]; do not supply round-trip efficiency twice |
| `auxiliary_kw_ac` | Constant storage-system AC demand, including any modelled auxiliaries |
| `interval_minutes` | Integer 1-60; every sample represents this whole interval |

For balanced storage, each phase receives one third of the total configured power.
The configured ratings must already be feasible for the equipment. The program
cannot infer that feasibility from the energy dataset.

Reject NaN, infinity, booleans masquerading as numbers, negative demand/generation,
invalid SOC bounds and malformed configuration. This first implementation uses
the canonical Draft 2020-12 schema at `schemas/energy-project.schema.json` through
`SchemaRegistry` for both init and build, followed by strict Python scenario validation.
The schema defines the closed v1 envelope and field bounds; Python additionally
rejects non-finite numbers and float-valued integer fields and enforces cross-field
SOC and topology constraints. Both validations are required. A separate CLI `--root`
selects the private workspace, not a replacement schema policy. Installed wheels
carry the canonical schema. The optional additive `site_facts` array records typed
facts (`fact_id`, `subject`, `property`, scalar `value`, optional `unit`, status,
and source/optional segment ID links). Statuses are `observed`, `source_reported`,
`inference`, `assumption`, or `unknown`; the contract intentionally has no
`verified` status. Observed/source-reported/inference facts require evidence links.
Linked source and segment records are read locally, checked against canonical
schemas and filename IDs, and pinned by byte hash in the preflight and build
manifest. They are never registered or modified by this tool. Reports include
fact values and evidence IDs/hashes, not source titles, locators or passage text.
This establishes referential integrity and reproducibility, not truth, authority,
engineering verification or approval. Legacy `evidence_refs` remain untouched and
unvalidated. Broader site/equipment/measurement/review schemas and workflow support
remain planned.

## Measurement CSV

One phase:

```csv
timestamp,load_l1_kw,pv_l1_kw
2025-01-01T00:00:00+00:00,0.4,0
2025-01-01T00:15:00+00:00,0.6,0
```

Three phases:

```csv
timestamp,load_l1_kw,pv_l1_kw,load_l2_kw,pv_l2_kw,load_l3_kw,pv_l3_kw
2025-01-01T00:00:00+00:00,0.4,0,0.5,0,0.3,0
2025-01-01T00:15:00+00:00,0.6,0,0.5,0,0.3,0
```

These are **interval-average kW**, not cumulative meter registers or interval kWh.
`timestamp` is the interval start and needs an explicit UTC offset. Normalise to UTC
before checking spacing. Gaps, duplicate/unsorted timestamps and column mismatches
are rejected, not silently interpolated. The final interval ends one configured
interval after the last timestamp. The user must verify that the original export
uses these semantics. Raw P1/supplier/PVGIS adapters are not implemented yet.

### Read-only profile preflight

Run `polder-energy --root /private/workspace preflight PROJECT_ID` before building.
It prints deterministic JSON to stdout and writes no files or run directories.
Exit 0 means the CSV passes this exact contract; exit 2 means rejected data or an
input/configuration error. CSV failures are JSON reports; missing files, invalid
project configuration and unknown scenarios are errors on stderr. A complete
scenario is required to supply explicit phase count and interval duration.

The report includes input byte hashes and data class, declared units and phase
channels, interval count, UTC start and exclusive end, covered duration, and kWh
integrals per input channel (`channel_energy_kwh` keys retain the CSV column names).
Rejected profiles have no energy totals or coverage: nothing is repaired, filled,
interpolated, annualised or silently split among phases. Unrepresentable time or
energy totals are also rejected by the report. The existing build/parser gate is
unchanged and remains authoritative for builds.

Errors use logical CSV record numbers (header is row 1), not physical line numbers
for quoted multiline records. Header mismatch stops inspection. Row diagnostics
collect multiple invalid records; spacing checks resume between valid adjacent
records after a malformed record, so the list is not an exhaustive defect inventory.
Blank lines retain the existing CSV parser behaviour. The final interval is counted
in full; this is observed-file coverage, not completeness against a requested date
range. There is no requested date range in the v1 contract.

Passing syntax does not establish source accuracy: original units, phase assignments
and the physical load/PV meter boundaries remain explicitly unverified. Agents must
check them against private source evidence; this command is not a vendor adapter,
installation approval, simulation or permission to publish customer telemetry.

## Equations and accounting

For interval duration `dt` hours, stored battery energy `E`, load `L_i`, PV `PV_i`,
and constant storage auxiliary power `A`:

```text
N = sum_i(L_i - PV_i) + A
E_min = nominal_kwh * minimum_soc
E_max = nominal_kwh * maximum_soc

When N < 0:
  charge_ac = min(-N, charge_limit_kw_ac, (E_max - E)/(eta_charge * dt))
  E_next = E + charge_ac * eta_charge * dt

When N >= 0:
  discharge_ac = min(N, discharge_limit_kw_ac, (E - E_min) * eta_discharge/dt)
  E_next = E - discharge_ac * dt/eta_discharge
```

There is no simultaneous charge/discharge command within an interval. Distribute
battery and auxiliary powers according to the selected topology. Compute the
signed physical power on each phase first; only then sum it for meter accounting.
Positive grid power means import. Baseline results exclude battery auxiliaries
because the baseline has no battery.

Check conservation over the run:

```text
PV + grid_import = load + grid_export + auxiliary_loss
                   + conversion_loss + (final_stored_energy - initial_stored_energy)
```

Initial stored energy is not free recurring value. Every run discloses its initial
and final energy. Short-period results are not annualised and are not converted to
payback. For option economics, compare equivalent SOC boundaries or explicitly
account for the terminal energy, then apply a separately validated tariff model.

Each supported one-phase or balanced-three-phase storage replay reports an
arithmetic comparison against a no-storage baseline calculated from the **same
validated samples and interval window**. It includes phase-summed meter import/
export and per-phase interval-average peaks. The baseline has no battery
auxiliaries; the storage concept includes its configured auxiliary demand and
conversion losses. Signed `baseline_minus_concept_*` values are differences, not
savings, guaranteed performance, or an economics result. The comparison is not
normalized for battery energy: inspect its initial/final/delta stored energy and
losses before interpreting it. Only one storage topology is simulated per run;
comparing alternative storage concepts requires separate, explicitly linked runs
with identical profile hashes and disclosed model/scenario inputs; project hashes
will differ when their scenario differs. Per-phase active-power peaks are not
RMS-current or fuse/protection evidence.

`dc_current_a(P_ac_kw, V_battery_min, efficiency)` implements
`1000 * P_ac_kw / (V_battery_min * efficiency)`. It is a steady-state estimate only,
not a fuse, conductor, contactor, cell-power or BMS sizing algorithm.

## Reproducibility and release limits

The run ID hashes project bytes, profile bytes, engine source, model version and
Python version. When typed fact links exist, the run identity also includes the
sorted evidence-record IDs, statuses and byte hashes. `manifest.json` records those
evidence fingerprints and output SHA-256 hashes, not copied source or segment
contents. Repeat runs with the same inputs/runtime reuse an identical bundle;
modified bundles are not overwritten.
Hashes detect changes, not authorship or tamper-proof approval. Cross-platform
bitwise identity across different Python versions is not claimed.

The run bundle stores hashes, not snapshots, of `project.json`, `profile.csv`, or
linked evidence records. Keep or archive those inputs and evidence separately if a
run must remain replayable after the files change or are moved. Single-phase topology drawings label the
selected battery phase; they remain functional concepts, not verified wiring plans.

All diagrams and reports say **CONCEPT ONLY - NOT FOR INSTALLATION**. The only
implemented release status is `concept_only`; filling every input cannot promote it.

## Test obligations for every new calculator

Provide hand-worked cases, units and reference methods; invalid-input and boundary
tests; conservation/monotonicity properties where applicable; independent numerical
comparison; documented validity envelope; a review owner; and a regression fixture
for every field defect. New claims need new tests, not just a new UI label.

For the next phase-aware/current model, explicitly test net-zero billing while one
phase remains overloaded, unknown power factor, missing current samples and a
battery-unavailable fallback. Never approve a connection downgrade from this v0 replay.
